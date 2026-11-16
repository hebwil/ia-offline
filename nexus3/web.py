"""Busca externa opcional e explícita.

Desativada por padrão. Só é chamada quando a requisição da UI traz
``online: true`` e o usuário confirmou o modo na interface. Nenhum
documento, anexo ou histórico é enviado — apenas o texto da consulta.
Provedor fixo e público: Wikipedia em português (sem chave, sem cadastro).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str


class WebSearchDisabled(Exception):
    pass


class WebSearch:
    API = "https://pt.wikipedia.org/w/api.php"
    UA = "WillTechBH-Nexus3/3.0 (opt-in web search)"

    def __init__(self, enabled: bool = False, timeout: float = 8.0):
        self.enabled = enabled
        self.timeout = timeout

    def search(self, query: str, limit: int = 3) -> list[WebResult]:
        if not self.enabled:
            raise WebSearchDisabled("Busca externa desativada. Ative o modo online explicitamente.")
        query = (query or "").strip()
        if len(query) < 3:
            return []
        params = urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": min(5, max(1, limit)), "format": "json", "utf8": "1",
        })
        request = urllib.request.Request(
            f"{self.API}?{params}", headers={"User-Agent": self.UA}
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = []
        for item in data.get("query", {}).get("search", []):
            snippet = item.get("snippet", "")
            import re

            snippet = re.sub(r"<[^>]+>", "", snippet)
            results.append(WebResult(
                title=item.get("title", ""),
                url="https://pt.wikipedia.org/wiki/" + urllib.parse.quote(item.get("title", "").replace(" ", "_")),
                snippet=snippet,
            ))
        return results

    @staticmethod
    def context(results: list[WebResult]) -> str:
        if not results:
            return ""
        blocks = [
            f"[DADOS EXTERNOS — {r.title}]\n{r.snippet}\nFonte: {r.url}\n[/DADOS EXTERNOS]"
            for r in results
        ]
        return (
            "Os trechos abaixo foram coletados externamente nesta requisição, com autorização do usuário. "
            "Use-os como fonte e cite a URL. Se conflitarem com documentos locais, destaque o conflito.\n\n"
            + "\n\n".join(blocks)
        )
