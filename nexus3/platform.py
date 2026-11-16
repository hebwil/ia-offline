"""Detecção de plataforma e resolução portátil de caminhos.

Nenhum caminho absoluto do host é gravado em configuração. A raiz é
descoberta em cada execução, portanto trocar a letra do drive no Windows
ou o ponto de montagem em macOS/Linux não exige reconfiguração.
"""

from __future__ import annotations

import os
import platform as _platform
import stat
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformInfo:
    system: str  # windows | darwin | linux
    machine: str  # x86_64 | arm64 | ...
    arch: str  # x64 | arm64 | other
    exe_suffix: str
    python: str
    raw_system: str

    @property
    def engine_key(self) -> str:
        """Chave usada no manifesto de binários oficiais do llama.cpp."""
        if self.system == "windows":
            return "win-cpu-arm64" if self.arch == "arm64" else "win-cpu-x64"
        if self.system == "darwin":
            return "macos-arm64" if self.arch == "arm64" else "macos-x64"
        if self.system == "linux":
            return "ubuntu-arm64" if self.arch == "arm64" else "ubuntu-x64"
        return f"unsupported-{self.arch}"


def detect_platform() -> PlatformInfo:
    raw = _platform.system().lower()
    system = "windows" if raw.startswith("win") else ("darwin" if raw == "darwin" else ("linux" if raw == "linux" else "unknown"))
    machine = _platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "other"
    return PlatformInfo(
        system=system,
        machine=machine,
        arch=arch,
        exe_suffix=".exe" if system == "windows" else "",
        python=_platform.python_version(),
        raw_system=_platform.system(),
    )


_MARKERS = ("nexus3.py", "MANIFEST.json", "pyproject.toml")


def find_root(start: str | os.PathLike[str] | None = None) -> Path:
    """Descobre a raiz portátil subindo a partir de ``start``.

    Ordem: variável de ambiente NEXUS3_ROOT → diretório informado →
    diretório do pacote → diretório de trabalho atual.
    """
    env = os.environ.get("NEXUS3_ROOT")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    here = Path(start).resolve() if start else Path(__file__).resolve()
    candidates.append(here if here.is_dir() else here.parent)
    candidates.append(Path.cwd())

    for candidate in candidates:
        cur = candidate.resolve()
        for _ in range(8):
            if any((cur / marker).exists() for marker in _MARKERS):
                return cur
            parent = cur.parent
            if parent == cur:
                break
            cur = parent
    raise RuntimeError("Raiz do Nexus 3.0 não encontrada. Defina NEXUS3_ROOT.")


def portable_path(root: str | os.PathLike[str], *parts: str) -> Path:
    """Junta caminhos garantindo que o resultado permaneça dentro de ``root``."""
    base = Path(root).resolve()
    target = base.joinpath(*[str(p) for p in parts]).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Caminho fora da raiz portátil: {target}") from exc
    return target


def ensure_executable(path: str | os.PathLike[str]) -> None:
    if os.name == "nt":
        return
    p = Path(path)
    if not p.exists():
        return
    mode = p.stat().st_mode
    if not mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP)


def describe_filesystem(path: str | os.PathLike[str]) -> str:
    """Melhor esforço para identificar o sistema de arquivos do volume."""
    p = Path(path)
    if os.name == "nt":
        try:
            import subprocess

            drive = str(p.drive or p.anchor)
            out = subprocess.run(
                ["fsutil", "fsinfo", "fsvolumeinfo", drive],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for fs in ("ntfs", "exfat", "fat32", "refs"):
                if fs in out:
                    return fs
        except Exception:
            pass
        return "unknown"
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["diskutil", "info", "-plist", str(p)],
                capture_output=True, text=True, timeout=6,
            ).stdout.lower()
            for fs in ("apfs", "exfat", "ms-dos fat32", "hfs+"):
                if fs in out:
                    return "exfat" if "ms-dos fat32" in fs else fs.split()[0]
        except Exception:
            pass
        return "unknown"
    try:
        for line in Path("/proc/mounts").read_text(errors="replace").splitlines():
            parts = line.split()
            if len(parts) > 2 and str(p).startswith(parts[1]):
                return parts[2]
    except Exception:
        pass
    return "unknown"
