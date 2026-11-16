"""Controles de segurança da v3.0.

- PathGuard: impede travessia de diretório e acesso fora da raiz portátil.
- redact: remove segredos e identificadores de host de logs e mensagens.
- ProcessRegistry: registra e encerra somente processos criados por esta app.
- AtomicWriter: escrita atômica com backup da versão anterior.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .platform import portable_path

_SECRET_PATTERNS = [
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;}\"']{6,})"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{10,})"),
    re.compile(r"(?i)(hf_[A-Za-z0-9]{12,})"),
]
_PATH_PATTERNS = [
    re.compile(r"(?<![\w])/Users/[^/\s\"']+"),
    re.compile(r"(?<![\w])/home/[^/\s\"']+"),
    re.compile(r"(?<![\w])[A-Za-z]:\\Users\\[^\\\s\"']+"),
]


def redact(text: str) -> str:
    """Redata chaves, tokens e diretórios pessoais em texto de log."""
    out = str(text or "")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups > 1:
            out = pattern.sub(lambda m: m.group(1) + "[REDACTADO]", out)
        else:
            out = pattern.sub("[REDACTADO]", out)
    for pattern in _PATH_PATTERNS:
        out = pattern.sub("[CAMINHO-REDATADO]", out)
    return out


class PathGuard:
    """Valida que todo caminho usado pela app está dentro da raiz."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).resolve()

    def resolve(self, *parts: str, must_exist: bool = False) -> Path:
        path = portable_path(self.root, *parts)
        if must_exist and not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado na raiz portátil: /{'/'.join(parts)}")
        return path

    def relative(self, path: str | os.PathLike[str]) -> str:
        resolved = Path(path).resolve()
        resolved.relative_to(self.root)
        return resolved.relative_to(self.root).as_posix()


class AtomicWriter:
    """Escreve JSON de forma atômica e mantém backup da versão anterior."""

    def __init__(self, root: str | os.PathLike[str]):
        self.guard = PathGuard(root)
        self.root = self.guard.root
        self._lock = threading.RLock()

    def write_json(self, rel_path: str, data: Any, backup: bool = True) -> Path:
        target = self.guard.resolve(*rel_path.split("/"))
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=False)
                handle.flush()
                os.fsync(handle.fileno())
            if backup and target.exists():
                backup_dir = self.guard.resolve("data", "backups")
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy2(target, backup_dir / f"{target.stem}-{stamp}{target.suffix}")
            os.replace(tmp, target)
        return target

    def write_bytes(self, rel_path: str, payload: bytes, backup: bool = False) -> Path:
        target = self.guard.resolve(*rel_path.split("/"))
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(payload)
            if backup and target.exists():
                backup_dir = self.guard.resolve("data", "backups")
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy2(target, backup_dir / f"{target.stem}-{stamp}{target.suffix}")
            os.replace(tmp, target)
        return target


def load_json(path: str | os.PathLike[str], default: Any = None, max_bytes: int = 20_000_000) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    if p.stat().st_size > max_bytes:
        raise ValueError(f"Arquivo JSON muito grande: {p.name}")
    with p.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class ProcessRegistry:
    """Rastreia PIDs iniciados pela app e permite encerramento verificado.

    Um PID só é encerrado se (a) foi registrado por esta instância e (b) a
    linha de comando atual contém o caminho do binário esperado. Isso evita
    o bug da v2.0, que matava processos por reaproveitamento de PID.
    """

    def __init__(self):
        self._entries: dict[int, dict[str, str]] = {}
        self._lock = threading.RLock()

    def register(self, pid: int, binary: str, label: str = "") -> None:
        with self._lock:
            self._entries[int(pid)] = {"binary": str(binary), "label": label}

    def unregister(self, pid: int) -> None:
        with self._lock:
            self._entries.pop(int(pid), None)

    @staticmethod
    def command_line(pid: int) -> str:
        """Obtém a linha de comando/caminho do executável sem depender de `ps`.

        Em macOS, `ps` pode ser bloqueado por políticas de sandbox; usamos
        `proc_pidpath` via ctypes (API pública do libSystem). Em Linux, /proc
        fornece a linha completa. No Windows, WMI via PowerShell.
        """
        try:
            if os.name == "nt":
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                    capture_output=True, text=True, timeout=6,
                ).stdout
                return out.strip()
            if Path(f"/proc/{int(pid)}/cmdline").exists():
                raw = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
                return raw.replace(b"\x00", b" ").decode(errors="replace")
            if sys.platform == "darwin":
                import ctypes
                import ctypes.util

                libc_path = ctypes.util.find_library("c")
                if not libc_path:
                    return ""
                libc = ctypes.CDLL(libc_path)
                buffer = ctypes.create_string_buffer(1024)
                libc.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
                libc.proc_pidpath.restype = ctypes.c_int
                length = libc.proc_pidpath(int(pid), buffer, ctypes.sizeof(buffer))
                if length > 0:
                    return buffer.value.decode(errors="replace")
            out = subprocess.run(
                ["ps", "-p", str(int(pid)), "-o", "command="],
                capture_output=True, text=True, timeout=6,
            ).stdout
            return out.strip()
        except Exception:
            return ""

    def owns(self, pid: int) -> bool:
        with self._lock:
            entry = self._entries.get(int(pid))
        if not entry:
            return False
        cmdline = self.command_line(pid)
        binary = Path(entry["binary"]).name.lower()
        return bool(cmdline) and binary in cmdline.lower()

    def stop(self, pid: int, timeout: float = 5.0) -> bool:
        if not self.owns(pid):
            self.unregister(pid)
            return False
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(int(pid))], capture_output=True, timeout=timeout)
            else:
                os.kill(int(pid), 15)
            for _ in range(int(timeout * 10)):
                if not self.command_line(pid):
                    break
                import time

                time.sleep(0.1)
            else:
                if os.name != "nt":
                    os.kill(int(pid), 9)
        except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
            pass
        finally:
            self.unregister(pid)
        return True

    def stop_all(self) -> list[int]:
        stopped = []
        for pid in list(self._entries):
            if self.stop(pid):
                stopped.append(pid)
        return stopped

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"pid": pid, **entry, "alive": self.command_line(pid) != ""}
                for pid, entry in self._entries.items()
            ]
