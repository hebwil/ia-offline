"""Ciclo de vida do llama-server com binários oficiais verificados.

Somente processos iniciados por esta classe são encerrados, e somente
após confirmação da linha de comando (ver ProcessRegistry).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .config import Config
from .hardware import HardwareProfile
from .models import DownloadCancelled, ModelFile, ProgressCallback, ModelSpec, sha256_file
from .platform import PlatformInfo, ensure_executable
from .security import AtomicWriter, PathGuard, ProcessRegistry, redact

# SHA-256 obtidos do campo `digest` da GitHub API em 2026-11-16.
ENGINE_BUILD = "b12444"
ENGINE_MANIFEST: dict[str, dict[str, Any]] = {
    "win-cpu-x64": {
        "file": f"llama-{ENGINE_BUILD}-bin-win-cpu-x64.zip",
        "sha256": "d17f82517cf6b5ee501953cc41ca1cdea0c2fb2a0aedd62b5c61e7b4fa6437bd",
        "size": 25219626,
    },
    "win-cpu-arm64": {
        "file": f"llama-{ENGINE_BUILD}-bin-win-cpu-arm64.zip",
        "sha256": "5891fac3aa22b5a8bc0cdb942b9dda52431cc01c4aed92653812cf7413b7ce11",
        "size": 13563027,
    },
    "macos-arm64": {
        "file": f"llama-{ENGINE_BUILD}-bin-macos-arm64.tar.gz",
        "sha256": "e1c00b152caa8c76680a0fbf3029b28b679f904b8fc2d8be9401f74cf41c46e1",
        "size": 17011663,
    },
    "macos-x64": {
        "file": f"llama-{ENGINE_BUILD}-bin-macos-x64.tar.gz",
        "sha256": "f5fc545dfbedef6b7d2fc8be0382e07ce63b2f9b10f8f80cb650132d4cb8c100",
        "size": 12768949,
    },
    "ubuntu-x64": {
        "file": f"llama-{ENGINE_BUILD}-bin-ubuntu-x64.tar.gz",
        "sha256": "0c95d7980612331f0ea472efd43b7697739e884f077fe0d5e6bc69f377d4753b",
        "size": 23465780,
    },
    "ubuntu-arm64": {
        "file": f"llama-{ENGINE_BUILD}-bin-ubuntu-arm64.tar.gz",
        "sha256": "bf2fbd41b0743c3a3a4ca78011a5f34697b7dce2db44914d538881ff4490c21c",
        "size": 19096283,
    },
}
ENGINE_URL_TEMPLATE = "https://github.com/ggml-org/llama.cpp/releases/download/{build}/{file}"


@dataclass
class RunningEngine:
    pid: int
    port: int
    model_id: str
    backend: str
    context: int
    started_at: float
    log_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid, "port": self.port, "model_id": self.model_id,
            "backend": self.backend, "context": self.context,
            "started_at": self.started_at, "log_path": self.log_path,
        }


class EngineError(RuntimeError):
    pass


def _safe_extract_archive(archive: Path, destination: Path) -> None:
    """Extrai com verificação de travessia, preservando links simbólicos relativos.

    Os pacotes oficiais macOS usam symlinks versionados (libllama.1.dylib →
    libllama.1.0.0.dylib). Ignorá-los quebra o motor com dyld "Library not
    loaded". Links absolutos e links que saem do diretório são rejeitados.
    """
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    def checked(target: Path) -> Path:
        resolved = (destination / target).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Arquivo com caminho inválido no pacote: {target}") from exc
        return resolved

    def checked_link(target: Path, linkname: str) -> str:
        if not linkname or Path(linkname).is_absolute() or "\\" in linkname:
            raise ValueError(f"Link simbólico absoluto rejeitado: {linkname}")
        resolved = (target.parent / linkname).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Link simbólico fora do pacote: {linkname}") from exc
        return linkname

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = checked(Path(info.filename))
                target.parent.mkdir(parents=True, exist_ok=True)
                mode = info.external_attr >> 16
                if os.name != "nt" and stat.S_ISLNK(mode):
                    linkname = zf.read(info).decode("utf-8", errors="replace").strip()
                    if target.exists() or target.is_symlink():
                        target.unlink()
                    target.symlink_to(checked_link(target, linkname))
                    continue
                with zf.open(info) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
                if os.name != "nt" and mode & 0o111:
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                target = checked(Path(member.name))
                if member.issym():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() or target.is_symlink():
                        target.unlink()
                    target.symlink_to(checked_link(target, member.linkname))
                    continue
                if member.islnk():
                    raise ValueError(f"Hard link rejeitado no pacote: {member.name}")
                if not member.isfile():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tf.extractfile(member)
                if source is None:
                    continue
                with source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
                if os.name != "nt" and member.mode & 0o111:
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


class EngineManager:
    def __init__(self, root: Path, platform_info: PlatformInfo, hardware: HardwareProfile, config: Config):
        self.root = Path(root).resolve()
        self.platform_info = platform_info
        self.hardware = hardware
        self.config = config
        self.guard = PathGuard(root)
        self.processes = ProcessRegistry()
        self.running: RunningEngine | None = None
        self.vision: RunningEngine | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ binário

    @property
    def engine_dir(self) -> Path:
        return self.guard.resolve("bin", "engines", self.platform_info.engine_key)

    def binary_path(self) -> Path | None:
        if not self.engine_dir.exists():
            return None
        name = "llama-server" + self.platform_info.exe_suffix
        candidates = list(self.engine_dir.rglob(name))
        return candidates[0] if candidates else None

    def engine_info(self) -> dict[str, Any]:
        manifest = ENGINE_MANIFEST.get(self.platform_info.engine_key)
        binary = self.binary_path()
        installed = bool(binary)
        verified = False
        verification = "nao-verificado"
        marker_rel = f"state/engine-{self.platform_info.engine_key}-sha256.txt"
        marker = self.guard.resolve(*marker_rel.split("/"))
        if installed and manifest:
            # Verifica o BINÁRIO instalado, não o arquivo baixado. O marker
            # antigo continha o hash do arquivo; isso era interpretado como
            # falha permanente. Migramos somente se o arquivo oficial também
            # conferir com o hash publicado.
            try:
                archive = self.engine_dir / manifest["file"]
                expected = marker.read_text(encoding="ascii").strip().lower() if marker.exists() else ""
                if expected == str(manifest["sha256"]).lower():
                    expected = ""
                if not expected and archive.is_file():
                    if sha256_file(archive) == str(manifest["sha256"]).lower():
                        expected = sha256_file(binary)
                        AtomicWriter(self.root).write_bytes(
                            marker_rel, expected.encode("ascii")
                        )
                        verification = "binario-derivado-de-arquivo-oficial"
                verified = bool(expected) and sha256_file(binary) == expected
                if verified and verification == "nao-verificado":
                    verification = "binario-verificado"
                if not verified and archive.is_file():
                    verification = "arquivo-oficial-divergente-do-binario"
            except OSError:
                verified = False
                verification = "indisponivel"
        return {
            "key": self.platform_info.engine_key,
            "build": ENGINE_BUILD,
            "installed": installed,
            "binary": str(binary.relative_to(self.root)) if binary else "",
            "archive_present": bool(manifest and (self.engine_dir / manifest["file"]).exists()),
            "archive_verified": verified,
            "verification": verification,
            "download_url": ENGINE_URL_TEMPLATE.format(build=ENGINE_BUILD, file=manifest["file"]) if manifest else "",
            "sha256": manifest["sha256"] if manifest else "",
            "size_bytes": manifest["size"] if manifest else 0,
            "supported": manifest is not None,
        }

    def ensure_binary(self, callback: ProgressCallback | None = None) -> Path:
        binary = self.binary_path()
        if binary:
            ensure_executable(binary)
            return binary
        manifest = ENGINE_MANIFEST.get(self.platform_info.engine_key)
        if not manifest:
            raise EngineError(
                f"Não há binário oficial verificado para {self.platform_info.system}/{self.platform_info.arch}. "
                "Compile llama.cpp localmente ou use outra plataforma."
            )
        if not self.config.get("downloads.allow_external"):
            raise PermissionError(
                "Instalação do motor exige autorização. Execute: nexus3.py setup --yes "
                "(usa " + manifest["sha256"] + " como verificação)."
            )
        item = ModelFile(
            path=f"bin/engines/{self.platform_info.engine_key}/{manifest['file']}",
            url=ENGINE_URL_TEMPLATE.format(build=ENGINE_BUILD, file=manifest["file"]),
            sha256=manifest["sha256"], size=int(manifest["size"]),
        )
        from .models import DownloadManager

        archive = DownloadManager(self.root, self.config).download_file(item, callback, key="engine")
        _safe_extract_archive(archive, self.engine_dir)
        binary = self.binary_path()
        if not binary:
            raise EngineError("O pacote oficial não continha llama-server.")
        ensure_executable(binary)
        AtomicWriter(self.root).write_bytes(
            f"state/engine-{self.platform_info.engine_key}-sha256.txt",
            sha256_file(binary).encode("ascii"),
        )
        return binary

    # --------------------------------------------------------------- execução

    @staticmethod
    def _free_port(preferred: int = 9931) -> int:
        import socket

        for candidate in range(preferred, preferred + 50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", candidate))
                    return candidate
                except OSError:
                    continue
        raise EngineError("Nenhuma porta livre entre 9931 e 9980.")

    def build_command(
        self,
        binary: Path,
        spec: ModelSpec,
        model_file: Path,
        port: int,
        context: int,
        gpu_layers: int,
        api_key: str,
        mmproj: Path | None = None,
    ) -> list[str]:
        cmd = [
            str(binary),
            "-m", str(model_file),
            "-c", str(context),
            "-np", "1",
            "-ngl", str(gpu_layers),
            "--host", "127.0.0.1",
            "--port", str(port),
            "--cors-origins", "localhost",
            "--api-key", api_key,
            "--no-context-shift",
        ]
        idle = int(self.config.get("engine.idle_sleep_seconds") or 0)
        if idle > 0:
            cmd += ["--sleep-idle-seconds", str(idle)]
        if mmproj is not None:
            cmd += ["-mm", str(mmproj), "--mmproj-offload"]
        return cmd

    def start(
        self,
        spec: ModelSpec,
        model_file: Path,
        context: int,
        gpu_layers: int,
        api_key: str,
        port: int | None = None,
        mmproj: Path | None = None,
        timeout: float = 90.0,
    ) -> RunningEngine:
        with self._lock:
            binary = self.binary_path()
            if not binary:
                raise EngineError("Motor não instalado. Execute 'nexus3.py setup --yes'.")
            port = port or self._free_port()
            cmd = self.build_command(binary, spec, model_file, port, context, gpu_layers, api_key, mmproj)
            log_dir = self.guard.resolve("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"engine-{port}.log"
            log_handle = log_path.open("ab", buffering=0)
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                proc = subprocess.Popen(
                    cmd, stdout=log_handle, stderr=subprocess.STDOUT,
                    cwd=str(self.root), creationflags=creationflags,
                )
            finally:
                log_handle.close()
            self.processes.register(proc.pid, str(binary), label=spec.id)
            running = RunningEngine(
                pid=proc.pid, port=port, model_id=spec.id, backend=self.platform_info.engine_key,
                context=context, started_at=time.time(), log_path=str(log_path.relative_to(self.root)),
            )
            # Atribui ANTES da sonda: se a health check falhar, stop() precisa
            # conhecer o PID recém-criado. Na v3.0 inicial isso vazava processo.
            self.running = running
            if not self.wait_health(port, timeout=timeout):
                self.processes.stop(proc.pid)
                self.running = None
                tail = ""
                try:
                    tail = redact(log_path.read_text(errors="replace")[-1200:])
                except OSError as exc:
                    tail = f"(log indisponível: {type(exc).__name__})"
                raise EngineError(
                    "llama-server não ficou pronto no prazo. Verifique o modelo e o log. "
                    + ("Últimas linhas: " + tail if tail else "")
                )
            return running

    def wait_health(self, port: int, timeout: float = 90.0) -> bool:
        deadline = time.time() + timeout
        url = f"http://127.0.0.1:{port}/health"
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return True
            except Exception:
                time.sleep(0.4)
        return False

    def stop(self) -> bool:
        with self._lock:
            if not self.running:
                return False
            stopped = self.processes.stop(self.running.pid)
            self.running = None
            return stopped

    def status(self) -> dict[str, Any]:
        engine = self.engine_info()
        running = self.running
        alive = False
        if running:
            alive = self.processes.owns(running.pid) and self._health_fast(running.port)
        return {
            **engine,
            "running": running.to_dict() if running else None,
            "alive": alive,
            "managed_processes": self.processes.snapshot(),
        }

    @staticmethod
    def _health_fast(port: int) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                return response.status == 200
        except Exception:
            return False

    # ---------------------------------------------------------- API compatível

    def _post_json(self, path: str, payload: dict[str, Any], api_key: str, timeout: float | None = None) -> dict[str, Any]:
        if not self.running:
            raise EngineError("Motor local não está em execução.")
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.running.port}{path}", data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout or self.config.get("engine.request_timeout_seconds", 120)) as response:
            return json.loads(response.read().decode("utf-8"))

    def chat(self, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        return self._post_json("/v1/chat/completions", payload, api_key)

    def embeddings(self, texts: list[str], api_key: str, model_id: str = "embedding") -> list[list[float]]:
        payload = {"model": model_id, "input": texts}
        result = self._post_json("/v1/embeddings", payload, api_key)
        return [item.get("embedding", []) for item in result.get("data", [])]

    def stream_chat(self, payload: dict[str, Any], api_key: str) -> Iterator[dict[str, Any]]:
        """Itera eventos SSE do llama-server já decodificados."""
        if not self.running:
            raise EngineError("Motor local não está em execução.")
        data = json.dumps({**payload, "stream": True}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.running.port}/v1/chat/completions", data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.get("engine.request_timeout_seconds", 120)) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    yield {"type": "done"}
                    return
                try:
                    yield json.loads(value)
                except json.JSONDecodeError:
                    continue

    def shutdown(self) -> list[int]:
        """Encerra todos os processos registrados por esta instância, inclusive
        os que falharam a health check ou foram trocados durante a sessão."""
        stopped = self.processes.stop_all()
        self.vision = None
        self.running = None
        return stopped
