"""Registro verificado de modelos e gerenciador de downloads.

Nenhum modelo é baixado sem consentimento explícito. Todo arquivo baixado
passa por verificação SHA-256 antes de ser promovido ao destino final.
"""

from __future__ import annotations

import hashlib
import os
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .hardware import HardwareProfile
from .security import PathGuard, load_json

ProgressCallback = Callable[[str, int, int, str], None]  # phase, done, total, message


@dataclass
class ModelFile:
    path: str
    url: str
    sha256: str
    size: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelFile":
        return cls(
            path=str(data["path"]), url=str(data["url"]),
            sha256=str(data.get("sha256") or ""), size=int(data.get("size") or 0),
        )


@dataclass
class ModelSpec:
    id: str
    name: str
    type: str
    category: str
    tags: list[str]
    capabilities: list[str]
    min_ram_gb: float
    recommended_ram_gb: float
    size_gb: float
    max_ctx: int
    quality: int
    priority: int
    license: str
    files: list[ModelFile] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelSpec":
        return cls(
            id=str(data["id"]), name=str(data["name"]), type=str(data.get("type", "text")),
            category=str(data.get("category", "general")),
            tags=[str(t) for t in data.get("tags", [])],
            capabilities=[str(c) for c in data.get("capabilities", [])],
            min_ram_gb=float(data.get("min_ram_gb", 0)),
            recommended_ram_gb=float(data.get("recommended_ram_gb", 0)),
            size_gb=float(data.get("size_gb", 0)), max_ctx=int(data.get("max_ctx", 4096)),
            quality=int(data.get("quality", 1)), priority=int(data.get("priority", 0)),
            license=str(data.get("license", "unknown")),
            files=[ModelFile.from_dict(f) for f in data.get("files", [])],
            notes=str(data.get("notes", "")),
        )

    @property
    def main_file(self) -> ModelFile | None:
        return self.files[0] if self.files else None

    def to_public_dict(self, root: Path) -> dict[str, Any]:
        installed, verified = installation_status(root, self)
        return {
            "id": self.id, "name": self.name, "type": self.type, "category": self.category,
            "tags": self.tags, "capabilities": self.capabilities,
            "min_ram_gb": self.min_ram_gb, "recommended_ram_gb": self.recommended_ram_gb,
            "size_gb": self.size_gb, "max_ctx": self.max_ctx, "quality": self.quality,
            "license": self.license, "notes": self.notes,
            "installed": installed, "verified": verified,
            "files": [
                {"path": f.path, "size": f.size, "sha256": f.sha256} for f in self.files
            ],
        }


class ModelRegistry:
    def __init__(self, root: Path, path: str = "config/models.json"):
        self.root = Path(root)
        self.path = path
        raw = load_json(self.root / path, default={}) or {}
        self.schema = int(raw.get("schema", 3))
        self.updated = str(raw.get("updated", ""))
        self.source = str(raw.get("source", ""))
        self.models: dict[str, ModelSpec] = {}
        for item in raw.get("models", []):
            spec = ModelSpec.from_dict(item)
            self.models[spec.id] = spec

    def get(self, model_id: str) -> ModelSpec | None:
        return self.models.get(model_id)

    def all(self) -> list[ModelSpec]:
        return list(self.models.values())

    def select(
        self,
        hardware: HardwareProfile,
        required_capabilities: set[str] | None = None,
        model_type: str | None = None,
        preferred_id: str = "",
        budget_gb: float | None = None,
        installed_only: bool = False,
    ) -> tuple[ModelSpec | None, str]:
        """Escolhe modelo por capacidade, memória e prioridade real.

        Retorna (modelo, justificativa). O modelo preferido do usuário é
        honrado quando cabe no orçamento e possui as capacidades pedidas.
        """
        caps = required_capabilities or {"chat"}
        budget = budget_gb if budget_gb is not None else hardware.budget_gb
        candidates = []
        for spec in self.models.values():
            if model_type and spec.type != model_type:
                continue
            if not caps.issubset(set(spec.capabilities)):
                continue
            if spec.min_ram_gb > hardware.ram_total_gb + 0.5:
                continue
            if not installed_only and spec.size_gb > budget + 0.6:
                continue
            if installed_only:
                ok, _ = installation_status(self.root, spec)
                if not ok:
                    continue
            score = spec.priority + spec.quality * 12
            score -= max(0.0, spec.size_gb - budget * 0.6) * 4
            if preferred_id and spec.id == preferred_id:
                score += 200
            if spec.min_ram_gb <= hardware.budget_gb:
                score += 20
            candidates.append((score, spec))

        if not candidates:
            return None, (
                f"Nenhum modelo atende capacidades={sorted(caps)}, tipo={model_type or 'qualquer'} "
                f"e orçamento={budget:.1f} GB. Instale um modelo compatível ou reduza a exigência."
            )
        candidates.sort(key=lambda item: item[0], reverse=True)
        best = candidates[0][1]
        reason = (
            f"{best.name}: prioridade {best.priority}, qualidade {best.quality}/4, "
            f"{best.size_gb:.2f} GB, RAM mínima {best.min_ram_gb} GB, "
            f"capacidades {', '.join(best.capabilities)}"
        )
        if best.id != preferred_id and preferred_id:
            reason += f" (preferência '{preferred_id}' não atendida pelo hardware/capacidades)"
        return best, reason


def sha256_file(path: str | os.PathLike[str], chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def installation_status(root: Path, spec: ModelSpec) -> tuple[bool, bool]:
    """Retorna (todos os arquivos presentes, todos os hashes conferem)."""
    guard = PathGuard(root)
    if not spec.files:
        return False, False
    present = True
    verified = True
    for item in spec.files:
        path = guard.resolve(*item.path.split("/"))
        if not path.exists():
            present = False
            verified = False
            continue
        if item.sha256:
            try:
                verified = verified and sha256_file(path) == item.sha256.lower()
            except OSError:
                verified = False
        else:
            verified = False
    return present, verified


class DownloadCancelled(Exception):
    pass


class DownloadManager:
    """Download resumível, com hash e promoção atômica."""

    def __init__(self, root: Path, config: Config):
        self.root = Path(root)
        self.config = config
        self.guard = PathGuard(root)
        self.cancel_event = threading.Event()
        self.active: dict[str, dict[str, Any]] = {}

    def cancel(self, key: str = "*") -> None:
        if key == "*":
            self.cancel_event.set()
        else:
            entry = self.active.get(key)
            if entry:
                entry["cancel"].set()

    def reset_cancellation(self) -> None:
        """Libera um novo ciclo de downloads após cancel('*')."""
        self.cancel_event.clear()

    def _progress(self, callback: ProgressCallback | None, phase: str, done: int, total: int, msg: str) -> None:
        if callback:
            try:
                callback(phase, done, total, msg)
            except Exception:
                pass

    def ensure_model(self, spec: ModelSpec, callback: ProgressCallback | None = None) -> list[Path]:
        if not self.config.get("downloads.allow_external"):
            raise PermissionError("Downloads externos não autorizados na configuração.")
        self.reset_cancellation()
        results = []
        for index, item in enumerate(spec.files):
            results.append(self.download_file(item, callback, key=f"{spec.id}:{index}"))
        return results

    def download_file(
        self, item: ModelFile, callback: ProgressCallback | None = None, key: str = ""
    ) -> Path:
        if not item.sha256 or len(item.sha256.strip()) != 64:
            raise ValueError(
                f"Download recusado: {item.path} não possui SHA-256 válido no registro. "
                "Integridade é obrigatória nesta versão."
            )
        target = self.guard.resolve(*item.path.split("/"))
        part = target.with_name(target.name + ".part")
        cancel = threading.Event()
        self.active[key or item.path] = {"cancel": cancel, "url": item.url}

        if target.exists() and item.sha256 and sha256_file(target) == item.sha256.lower():
            self._progress(callback, "verified", item.size, item.size, f"{target.name}: já verificado")
            return target

        done = part.stat().st_size if part.exists() else 0
        if item.size and done > item.size:
            part.unlink(missing_ok=True)
            done = 0

        headers = {"User-Agent": "WillTechBH-Nexus3/3.0"}
        if done:
            headers["Range"] = f"bytes={done}-"

        total = item.size or 0
        self._progress(callback, "start", done, total, f"Baixando {target.name}")
        request = urllib.request.Request(item.url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and not done:
                    total = int(content_length)
                mode = "ab" if done and response.status == 206 else "wb"
                if mode == "wb":
                    done = 0
                target.parent.mkdir(parents=True, exist_ok=True)
                with part.open(mode) as handle:
                    while True:
                        if cancel.is_set() or self.cancel_event.is_set():
                            raise DownloadCancelled(f"Download cancelado: {target.name}")
                        block = response.read(int(self.config.get("downloads.chunk_bytes") or 262144))
                        if not block:
                            break
                        handle.write(block)
                        done += len(block)
                        self._progress(callback, "download", done, total, target.name)
        except DownloadCancelled:
            raise
        finally:
            self.active.pop(key or item.path, None)
            # O sinal global de cancelamento NÃO é limpo automaticamente:
            # cancel('*') deve valer para todos os arquivos de um modelo.
            # Use reset_cancellation() para iniciar um novo ciclo.

        if not self.config.get("downloads.verify_hash", True):
            raise PermissionError("Verificação de hash desativada na configuração; download abortado por política.")
        actual = sha256_file(part)
        if actual.lower() != item.sha256.lower():
            part.unlink(missing_ok=True)
            raise ValueError(
                f"Hash inválido para {target.name}: esperado {item.sha256}, obtido {actual}. Arquivo removido."
            )
        self._progress(callback, "verified", done, total, f"Hash verificado: {target.name}")
        os.replace(part, target)
        return target
