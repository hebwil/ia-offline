"""RAG local: indexação lexical BM25 + embeddings opcionais.

A resposta fundamentada é construída pelo `grounded_prompt`, que separa
explicitamente trechos extraídos das fontes e instrui o modelo a identificar
inferências. Nenhum trecho é enviado para fora do projeto.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .documents import Chunk, Document, chunk_document
from .security import AtomicWriter, load_json

STOPWORDS = {
    "a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "que", "e", "ou",
    "mas", "se", "como", "mais", "muito", "me", "my", "the", "of", "and", "to", "in",
    "is", "are", "for", "on", "com", "pelo", "pela", "nos", "num", "numa", "esse",
    "essa", "isto", "aquilo", "seu", "sua", "qual", "quando", "onde", "porque",
}
EmbedFn = Callable[[list[str]], list[list[float]]]


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    tokens = re.findall(r"[a-z0-9_]+", normalized)
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    a = list(left)
    b = list(right)
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class SearchResult:
    text: str
    doc_path: str
    doc_name: str
    page: int
    position: int
    score: float
    source: str

    def citation(self) -> str:
        return f"{self.doc_name} (p. {self.page})" if self.page else self.doc_name

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "citation": self.citation()}


class DocumentStore:
    """Índice local persistente. Chunks são armazenados com o texto integral."""

    def __init__(self, root: Path, config=None, embed_fn: EmbedFn | None = None):
        self.root = Path(root)
        self.config = config
        self.embed_fn = embed_fn
        self.path = self.root / "data" / "docs" / "store.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = load_json(self.path, default={}) or {}
        self.chunks: list[dict[str, Any]] = list(data.get("chunks", []))
        self.documents: dict[str, dict[str, Any]] = dict(data.get("documents", {}))
        self._k1 = 1.5
        self._b = 0.75

    def save(self) -> None:
        AtomicWriter(self.root).write_json(
            "data/docs/store.json", {"chunks": self.chunks, "documents": self.documents}, backup=False
        )

    def clear(self) -> None:
        self.chunks = []
        self.documents = {}
        self.save()

    def index_document(self, doc: Document, chunk_chars: int | None = None, overlap: int | None = None) -> int:
        self.remove_document(doc.rel_path)
        chunk_chars = chunk_chars or (self.config.get("rag.chunk_chars") if self.config else None) or 1200
        overlap = overlap if overlap is not None else ((self.config.get("rag.chunk_overlap") if self.config else None) or 180)
        pieces: list[Chunk] = list(chunk_document(doc, chunk_chars, overlap))
        for piece in pieces:
            self.chunks.append({
                "text": piece.text, "doc_path": piece.doc_path, "doc_name": piece.doc_name,
                "page": piece.page, "position": piece.position,
                "tokens": piece.tokens_estimate, "tokens_vec": tokenize(piece.text),
            })
        self.documents[doc.rel_path] = {
            "name": doc.name, "kind": doc.kind, "chars": len(doc.text),
            "page_count": doc.page_count, "chunks": len(pieces), "warnings": doc.warnings,
        }
        self.save()
        return len(pieces)

    def remove_document(self, rel_path: str) -> int:
        before = len(self.chunks)
        self.chunks = [c for c in self.chunks if c.get("doc_path") != rel_path]
        self.documents.pop(rel_path, None)
        self.save()
        return before - len(self.chunks)

    def list_documents(self) -> list[dict[str, Any]]:
        return [{"path": key, **value} for key, value in self.documents.items()]

    def _bm25(self, query_tokens: list[str]) -> list[tuple[int, float]]:
        if not self.chunks or not query_tokens:
            return []
        total = len(self.chunks)
        avgdl = max(1.0, sum(len(c.get("tokens_vec", [])) for c in self.chunks) / total)
        df: Counter[str] = Counter()
        for chunk in self.chunks:
            for token in set(chunk.get("tokens_vec", [])):
                df[token] += 1
        idf = {
            token: math.log(1.0 + (total - freq + 0.5) / (freq + 0.5))
            for token, freq in df.items()
        }
        scores: list[tuple[int, float]] = []
        for index, chunk in enumerate(self.chunks):
            tf = Counter(chunk.get("tokens_vec", []))
            length = max(1, len(chunk.get("tokens_vec", [])))
            score = 0.0
            for token in query_tokens:
                if token not in tf:
                    continue
                freq = tf[token]
                score += idf.get(token, 0.0) * (freq * (self._k1 + 1)) / (
                    freq + self._k1 * (1 - self._b + self._b * length / avgdl)
                )
            if score > 0:
                scores.append((index, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores

    def search(self, query: str, top_k: int | None = None, use_embeddings: bool | None = None) -> list[SearchResult]:
        top_k = int(top_k or (self.config.get("rag.top_k") if self.config else None) or 5)
        query_tokens = tokenize(query)
        lexical = self._bm25(query_tokens)
        best: dict[int, float] = {index: score for index, score in lexical}
        max_lexical = max(best.values(), default=1.0) or 1.0

        want_embeddings = use_embeddings
        if want_embeddings is None:
            want_embeddings = bool(self.config and self.config.get("rag.use_embeddings"))
        if want_embeddings and self.embed_fn and self.chunks:
            try:
                vectors = self.embed_fn([query] + [c["text"] for c in self.chunks])
                if vectors and len(vectors) == len(self.chunks) + 1:
                    for index, vector in enumerate(vectors[1:]):
                        best[index] = best.get(index, 0.0) + max(0.0, cosine(vectors[0], vector)) * max_lexical
            except Exception:
                pass  # fallback lexical transparente

        ordered = sorted(best.items(), key=lambda item: item[1], reverse=True)[:top_k]
        results = []
        for index, score in ordered:
            chunk = self.chunks[index]
            results.append(SearchResult(
                text=chunk["text"], doc_path=chunk["doc_path"], doc_name=chunk["doc_name"],
                page=int(chunk.get("page") or 0), position=int(chunk.get("position") or 0),
                score=round(float(score), 4),
                source="hibrido" if want_embeddings and self.embed_fn else "lexical",
            ))
        return results

    def grounded_prompt(self, query: str, results: list[SearchResult], agent_prompt: str = "") -> str:
        blocks = []
        for index, result in enumerate(results, 1):
            blocks.append(
                f"[FONTE {index} — {result.citation()}]\n{result.text}\n[/FONTE {index}]"
            )
        sources = "\n\n".join(blocks)
        return (
            (agent_prompt + "\n\n" if agent_prompt else "")
            + "Você recebeu trechos extraídos de documentos locais do usuário.\n"
            + "REGRAS: (1) use apenas os trechos abaixo como base para afirmações sobre os documentos; "
            + "(2) cite a fonte e a página sempre que usar um trecho; (3) separade claramente "
            + "'Extraído do documento' de 'Inferência do modelo'; (4) se a informação não estiver "
            + "nos trechos, diga que não consta nos documentos — não invente.\n\n"
            + "PERGUNTA DO USUÁRIO:\n" + query + "\n\n"
            + "TRECHOS EXTRAÍDOS:\n" + (sources or "(nenhum trecho disponível)")
        )
