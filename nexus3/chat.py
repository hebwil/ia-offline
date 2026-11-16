"""Persistência de conversas dentro da raiz portátil."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .security import AtomicWriter, load_json


class ChatStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / "data" / "chats"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.writer = AtomicWriter(self.root)
        self.active = ""

    def new(self) -> str:
        sid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.writer.write_json(f"data/chats/{sid}.json", [], backup=False)
        self.active = sid
        return sid

    def path(self, sid: str) -> Path:
        if not sid or "/" in sid or "\\" in sid or ".." in sid:
            raise ValueError("ID de conversa inválido.")
        return self.dir / f"{sid}.json"

    def load(self, sid: str | None) -> list[dict[str, Any]]:
        sid = sid or self.active
        if not sid:
            return []
        return load_json(self.path(sid), default=[]) or []

    def append(self, role: str, content: str, source: str = "local", **extra: Any) -> None:
        sid = self.active or self.new()
        messages = self.load(sid)
        messages.append({
            "role": role, "content": content, "source": source,
            "at": datetime.now().isoformat(timespec="seconds"), **extra,
        })
        self.writer.write_json(f"data/chats/{sid}.json", messages, backup=True)

    def clear(self, sid: str | None = None) -> None:
        sid = sid or self.active
        if sid:
            self.writer.write_json(f"data/chats/{sid}.json", [], backup=True)

    def delete(self, sid: str) -> bool:
        path = self.path(sid)
        if path.exists():
            path.unlink()
            if self.active == sid:
                self.active = ""
            return True
        return False

    def list(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self.dir.glob("*.json"), reverse=True):
            messages = load_json(path, default=[]) or []
            first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
            items.append({
                "id": path.stem,
                "title": first[:60].strip() or f"Conversa {path.stem[:19]}",
                "messages": len(messages),
                "updated": messages[-1].get("at", "") if messages else "",
            })
        return items

    def search(self, term: str) -> list[dict[str, Any]]:
        needle = term.strip().lower()
        if not needle:
            return []
        hits = []
        for item in self.list():
            messages = self.load(item["id"])
            if any(needle in str(m.get("content", "")).lower() for m in messages):
                hits.append(item)
        return hits
