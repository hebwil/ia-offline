"""Detecção de hardware multiplataforma e perfis de execução.

Nunca inventa VRAM: se não há como consultar, reporta 0 e o router usa
fallback conservador para CPU. Nenhum dado de host é enviado para fora.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .security import redact


def _run(cmd: list[str], timeout: float = 6.0) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (result.stdout or "").strip()
    except Exception:
        return ""


@dataclass
class HardwareProfile:
    os: str
    arch: str
    cpu_model: str = "desconhecido"
    cpu_cores: int = 1
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    gpus: list[str] = field(default_factory=list)
    vram_total_gb: float = 0.0
    accelerations: list[str] = field(default_factory=list)
    filesystem: str = "unknown"
    portable: bool = True
    warnings: list[str] = field(default_factory=list)

    @property
    def tier(self) -> str:
        """modest | intermediate | advanced — usa RAM total e aceleração."""
        if self.ram_total_gb >= 24 or self.vram_total_gb >= 12:
            return "advanced"
        if self.ram_total_gb >= 10 or self.vram_total_gb >= 4:
            return "intermediate"
        return "modest"

    @property
    def budget_gb(self) -> float:
        """Memória que pode ser destinada ao modelo com segurança."""
        # macOS reporta "free + inactive" como disponível e desconta cache de
        # arquivos que pode ser purgado. Usamos no mínimo 60% da RAM total para
        # não subdimensionar contextos em máquinas com bastante memória.
        usable = max(self.ram_available_gb or 0.0, self.ram_total_gb * 0.60)
        usable = min(usable, self.ram_total_gb)
        return max(0.8, usable * (0.55 if self.vram_total_gb < 2 else 0.70))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tier"] = self.tier
        data["budget_gb"] = round(self.budget_gb, 2)
        return data


def _macos(profile: HardwareProfile) -> None:
    try:
        import sysctl

        total = int(sysctl.sysctlbyname("hw.memsize"))
        profile.ram_total_gb = round(total / 1024 ** 3, 2)
    except Exception:
        out = _run(["sysctl", "-n", "hw.memsize"])
        if out.isdigit():
            profile.ram_total_gb = round(int(out) / 1024 ** 3, 2)
    vm = _run(["vm_stat"])
    page_size = 4096
    m = re.search(r"page size of (\d+) bytes", vm)
    if m:
        page_size = int(m.group(1))
    free = re.search(r"Pages free:\s+(\d+)", vm)
    inactive = re.search(r"Pages inactive:\s+(\d+)", vm)
    if free or inactive:
        pages = int(free.group(1) if free else 0) + int(inactive.group(1) if inactive else 0)
        profile.ram_available_gb = round(pages * page_size / 1024 ** 3, 2)
    profile.cpu_model = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or _run(["sysctl", "-n", "hw.model"])
    profile.accelerations.append("metal")
    gpu = _run(["system_profiler", "SPDisplaysDataType"], timeout=12)
    for line in gpu.splitlines():
        if "Chipset Model:" in line or "Vendor:" in line:
            name = line.split(":", 1)[1].strip()
            if name and name not in profile.gpus:
                profile.gpus.append(redact(name))
        if "VRAM" in line or "Total Number of Cores" in line:
            continue


def _linux(profile: HardwareProfile) -> None:
    try:
        meminfo = {}
        for line in Path("/proc/meminfo").read_text(errors="replace").splitlines():
            key, _, rest = line.partition(":")
            meminfo[key] = rest.strip().split()[0] if rest.strip() else "0"
        kb = int(meminfo.get("MemTotal", "0"))
        profile.ram_total_gb = round(kb / 1024 ** 2, 2)
        profile.ram_available_gb = round(int(meminfo.get("MemAvailable", "0")) / 1024 ** 2, 2)
    except Exception:
        profile.warnings.append("Não foi possível ler /proc/meminfo.")
    cpuinfo = ""
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(errors="replace")
        match = re.search(r"model name\s*:\s*(.+)", cpuinfo)
        if match:
            profile.cpu_model = match.group(1).strip()
    except Exception:
        pass
    nvidia = _run([
        "nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits",
    ])
    for line in nvidia.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            profile.gpus.append(redact(parts[0]))
            try:
                profile.vram_total_gb = max(profile.vram_total_gb, round(float(parts[1]) / 1024, 2))
            except ValueError:
                pass
    if profile.gpus:
        profile.accelerations.append("cuda")
    if _run(["vulkaninfo", "--summary"], timeout=4):
        if "vulkan" not in profile.accelerations:
            profile.accelerations.append("vulkan")


def _windows(profile: HardwareProfile) -> None:
    ps = """
$cs = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpus = Get-CimInstance Win32_VideoController
[pscustomobject]@{
  ram = [math]::Round($cs.TotalPhysicalMemory/1GB,2)
  cpu = $cpu.Name
  gpus = @($gpus | ForEach-Object { $_.Name }) -join '|'
  vram = [math]::Round((($gpus | Measure-Object -Property AdapterRAM -Sum).Sum/1GB),2)
} | ConvertTo-Json -Compress
"""
    out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=12)
    if out:
        import json

        try:
            data = json.loads(out.splitlines()[-1])
            profile.ram_total_gb = float(data.get("ram") or 0)
            profile.cpu_model = redact(str(data.get("cpu") or "desconhecido"))
            profile.gpus = [redact(g) for g in str(data.get("gpus") or "").split("|") if g]
            profile.vram_total_gb = float(data.get("vram") or 0)
        except Exception:
            profile.warnings.append("Falha ao interpretar dados WMI; usando fallback.")
    if not profile.ram_total_gb:
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            profile.ram_total_gb = round(status.ullTotalPhys / 1024 ** 3, 2)
            profile.ram_available_gb = round(status.ullAvailPhys / 1024 ** 3, 2)
        except Exception:
            profile.warnings.append("Não foi possível consultar RAM no Windows.")
    if _run(["nvidia-smi", "-L"], timeout=4):
        profile.accelerations.append("cuda")
    if _run(["where", "vulkaninfo"], timeout=4):
        if "vulkan" not in profile.accelerations:
            profile.accelerations.append("vulkan")


def detect_hardware(platform_info, root: os.PathLike[str] | str | None = None, config: Config | None = None) -> HardwareProfile:
    """Monta o perfil de hardware usando apenas APIs locais."""
    profile = HardwareProfile(
        os=platform_info.system,
        arch=platform_info.arch,
        cpu_cores=os.cpu_count() or 1,
    )
    if platform_info.system == "darwin":
        _macos(profile)
    elif platform_info.system == "linux":
        _linux(profile)
    elif platform_info.system == "windows":
        _windows(profile)
    else:
        profile.warnings.append("Sistema operacional não suportado para detecção automática.")

    if root:
        from .platform import describe_filesystem

        profile.filesystem = describe_filesystem(root)
        if profile.filesystem in ("exfat", "fat32", "ms-dos fat32"):
            profile.warnings.append(
                f"Sistema {profile.filesystem}: permissões de execução e nomes longos podem ser limitados."
            )
    if config and config.get("engine.backend") not in (None, "", "auto"):
        profile.accelerations.insert(0, str(config.get("engine.backend")))
    return profile


def context_recommendation(profile: HardwareProfile, model_max_ctx: int = 8192) -> int:
    """Contexto seguro: limitado por RAM e pelo teto do modelo."""
    per_token_gb = 0.00035  # aproximação conservadora para KV cache Q8
    headroom = max(0.25, profile.budget_gb * 0.25)
    by_ram = int(headroom / per_token_gb)
    candidate = min(model_max_ctx, by_ram)
    for step in (32768, 16384, 8192, 4096, 2048, 1024):
        if candidate >= step:
            return step
    return 512


def gpu_layers_recommendation(profile: HardwareProfile) -> int:
    if profile.vram_total_gb >= 8:
        return 999
    if profile.vram_total_gb >= 4:
        return 24
    if profile.vram_total_gb >= 2:
        return 12
    return 0
