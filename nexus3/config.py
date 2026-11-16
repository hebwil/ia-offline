"""Configuração versionada e portátil da v3.0."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .platform import PlatformInfo, find_root
from .security import AtomicWriter, load_json

DEFAULTS: dict[str, Any] = {
    "schema": 3,
    "version": "3.0.0-develop",
    "product_name": "WillTechBH IA Nexus Portable 3.0",
    "language": "pt-BR",
    "defaults": {
        "mode": "offline",
        "theme": "dark",
        "context_strategy": "auto",
        "temperature": 0.7,
        "max_tokens": 1024,
    },
    "server": {"host": "127.0.0.1", "port": 0, "api_key": ""},
    "engine": {
        "build": "b12444",
        "backend": "auto",
        "auto_download_engine": False,
        "request_timeout_seconds": 120,
        "idle_sleep_seconds": 0,
    },
    "downloads": {"allow_external": False, "chunk_bytes": 262144, "verify_hash": True},
    "privacy": {
        "local_only_by_default": True,
        "online_opt_in_required": True,
        "store_host_name": False,
        "redact_logs": True,
        "send_documents_externally": False,
    },
    "tools": {
        "enabled": False,
        "allowlist": ["document_search", "calculator"],
        "require_confirmation": True,
    },
    "rag": {"chunk_chars": 1200, "chunk_overlap": 180, "top_k": 5, "use_embeddings": False},
}


@dataclass
class Config:
    root: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, root: str | os.PathLike[str] | None = None) -> "Config":
        base = Path(root) if root else find_root()
        stored = load_json(base / "config" / "nexus3.json", default={}) or {}
        merged = copy.deepcopy(DEFAULTS)
        _deep_merge(merged, stored if isinstance(stored, dict) else {})
        return cls(root=base, data=merged)

    def save(self) -> None:
        AtomicWriter(self.root).write_json("config/nexus3.json", self.data)

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def set(self, path: str, value: Any) -> None:
        keys = path.split(".")
        node = self.data
        for key in keys[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise ValueError(f"Configuração inválida: {path}")
        node[keys[-1]] = value

    def public_view(self) -> dict[str, Any]:
        """Cópia segura para a UI: sem chaves de API."""
        view = copy.deepcopy(self.data)
        server = view.get("server", {})
        if "api_key" in server:
            server["api_key"] = "***" if server["api_key"] else ""
        return view


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def install_id(root: Path) -> str:
    """ID anônimo e estável desta instalação, sem dados do host."""
    import hashlib
    import uuid

    path = Path(root) / "state" / "install-id.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        value = uuid.uuid4().hex
        path.write_text(value, encoding="ascii")
    return hashlib.sha256(path.read_text(encoding="ascii").strip().encode()).hexdigest()[:16]


def environment_summary(platform_info: PlatformInfo) -> dict[str, Any]:
    return {
        "os": platform_info.system,
        "arch": platform_info.arch,
        "python": platform_info.python,
        "nexus_root_env": bool(os.environ.get("NEXUS3_ROOT")),
        "offline_env": os.environ.get("NEXUS3_OFFLINE", ""),
    }
