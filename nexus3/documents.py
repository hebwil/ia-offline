"""Ingestão local de documentos: PDF, DOCX, TXT/MD/JSON, CSV, XLSX e imagens.

Nenhum documento é enviado a serviço externo. OCR é opcional e somente
executado se `tesseract` estiver disponível no host; caso contrário o
sistema informa a limitação em vez de inventar conteúdo.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree as ET

from .security import PathGuard, redact

_VENDOR = Path(__file__).parent / "vendor"
if _VENDOR.exists() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

MAX_BYTES = 25 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".log", ".py", ".js", ".ts", ".html", ".css", ".xml", ".yaml", ".yml", ".ini"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


@dataclass
class Document:
    name: str
    rel_path: str
    kind: str
    text: str
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "path": self.rel_path, "kind": self.kind,
            "chars": len(self.text), "page_count": self.page_count,
            "warnings": self.warnings, "preview": redact(self.text[:220]),
        }


class DocumentError(RuntimeError):
    pass


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class DocumentExtractor:
    def __init__(self, root: Path):
        self.guard = PathGuard(root)

    def extract_path(self, rel_path: str) -> Document:
        path = self.guard.resolve(*rel_path.split("/"), must_exist=True)
        if path.stat().st_size > MAX_BYTES:
            raise DocumentError(f"Arquivo maior que o limite de {MAX_BYTES // 1048576} MB: {path.name}")
        return self.extract(path, rel_path)

    def extract(self, path: Path, rel_path: str | None = None) -> Document:
        rel = rel_path or self.guard.relative(path)
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._pdf(path, rel)
        if ext == ".docx":
            return self._docx(path, rel)
        if ext == ".xlsx":
            return self._xlsx(path, rel)
        if ext == ".csv":
            return self._csv(path, rel)
        if ext in IMAGE_EXTENSIONS:
            return self._image(path, rel)
        if ext in TEXT_EXTENSIONS or ext == "":
            text = _decode(path.read_bytes())
            return Document(path.name, rel, "text", text)
        return Document(path.name, rel, "text", _decode(path.read_bytes()),
                        warnings=[f"Extensão '{ext}' tratada como texto simples."])

    # --------------------------------------------------------------- PDF

    def _pdf(self, path: Path, rel: str) -> Document:
        warnings: list[str] = []
        pages: list[str] = []
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            for index, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:
                    text = ""
                    warnings.append(f"Página {index}: falha ao extrair texto ({type(exc).__name__}).")
                pages.append(text)
        except Exception as exc:
            raise DocumentError(f"Não foi possível abrir o PDF: {type(exc).__name__}: {redact(str(exc))}") from exc
        text = "\n\n".join(f"[página {i}]\n{value}" for i, value in enumerate(pages, 1) if value.strip())
        if not text.strip():
            warnings.append(
                "PDF sem texto pesquisável. Pode ser digitalizado; use OCR local (tesseract) "
                "ou um modelo de visão. O Nexus não inventa o conteúdo."
            )
        return Document(path.name, rel, "pdf", text, len(pages), warnings, pages)

    # -------------------------------------------------------------- DOCX

    @staticmethod
    def _docx_text(xml_bytes: bytes) -> str:
        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for para in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            chunks = [node.text or "" for node in para.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")]
            value = "".join(chunks).strip()
            if value:
                paragraphs.append(value)
        return "\n".join(paragraphs)

    def _docx(self, path: Path, rel: str) -> Document:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n == "word/document.xml" or n.startswith("word/document")]
                if not names:
                    raise DocumentError("DOCX sem word/document.xml.")
                text = self._docx_text(archive.read(names[0]))
        except zipfile.BadZipFile as exc:
            raise DocumentError("DOCX inválido ou corrompido.") from exc
        return Document(path.name, rel, "docx", text)

    # -------------------------------------------------------------- XLSX

    def _xlsx(self, path: Path, rel: str, max_rows: int = 2000) -> Document:
        ns_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        try:
            with zipfile.ZipFile(path) as archive:
                shared: list[str] = []
                if "xl/sharedStrings.xml" in archive.namelist():
                    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                    for item in root.iter(ns_main + "si"):
                        shared.append("".join(t.text or "" for t in item.iter(ns_main + "t")))
                sheets = sorted(
                    n for n in archive.namelist()
                    if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
                )
                blocks: list[str] = []
                for sheet in sheets:
                    root = ET.fromstring(archive.read(sheet))
                    rows: list[str] = []
                    for row in root.iter(ns_main + "row"):
                        if len(rows) >= max_rows:
                            rows.append("[...] linhas omitidas pelo limite de segurança")
                            break
                        cells: list[str] = []
                        for cell in row.iter(ns_main + "c"):
                            value_node = cell.find(ns_main + "v")
                            inline = cell.find(ns_main + "is")
                            value = ""
                            if value_node is not None and value_node.text:
                                value = value_node.text
                                if cell.get("t") == "s":
                                    try:
                                        value = shared[int(value)]
                                    except (ValueError, IndexError):
                                        value = ""
                            elif inline is not None:
                                value = "".join(t.text or "" for t in inline.iter(ns_main + "t"))
                            cells.append(value.replace("\t", " ").replace("\n", " "))
                        rows.append("\t".join(cells))
                    blocks.append(f"[aba: {Path(sheet).stem}]\n" + "\n".join(rows))
                text = "\n\n".join(blocks)
        except zipfile.BadZipFile as exc:
            raise DocumentError("XLSX inválido ou corrompido.") from exc
        return Document(path.name, rel, "xlsx", text)

    # --------------------------------------------------------------- CSV

    def _csv(self, path: Path, rel: str, max_rows: int = 5000) -> Document:
        raw = path.read_bytes()
        text = _decode(raw)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows: list[list[str]] = []
        reader = csv.reader(io.StringIO(text), dialect)
        for index, row in enumerate(reader):
            if index >= max_rows:
                rows.append(["[...] linhas omitidas pelo limite de segurança"])
                break
            rows.append([cell.strip() for cell in row])
        rendered = "\n".join("\t".join(row) for row in rows)
        return Document(path.name, rel, "csv", rendered)

    # ------------------------------------------------------------ imagens

    def _image(self, path: Path, rel: str) -> Document:
        warnings = [
            "Imagem detectada. Para interpretar o conteúdo é necessário um modelo de visão "
            "ou OCR local. Nenhum texto será inventado."
        ]
        text = ""
        tesseract = shutil.which("tesseract")
        if tesseract:
            try:
                result = subprocess.run(
                    [tesseract, str(path), "stdout", "-l", "por+eng"],
                    capture_output=True, timeout=45,
                )
                text = result.stdout.decode("utf-8", errors="replace").strip()
                if text:
                    warnings[0] = "Texto extraído por OCR local (tesseract). Revise a precisão."
            except (subprocess.TimeoutExpired, OSError) as exc:
                warnings.append(f"OCR local falhou: {type(exc).__name__}.")
        else:
            warnings.append("tesseract não está disponível; OCR local não executado.")
        return Document(path.name, rel, "image", text, 0, warnings)


@dataclass(frozen=True)
class Chunk:
    text: str
    doc_path: str
    doc_name: str
    position: int
    page: int
    tokens_estimate: int


def chunk_document(doc: Document, chunk_chars: int = 1200, overlap: int = 180) -> Iterator[Chunk]:
    """Divide o documento preservando referência de arquivo/página."""
    chunk_chars = max(300, int(chunk_chars))
    overlap = max(0, min(overlap, chunk_chars // 4))
    blocks = doc.pages if doc.pages else [doc.text]
    position = 0
    for page_index, block in enumerate(blocks, start=1):
        if not block.strip():
            continue
        start = 0
        while start < len(block):
            end = min(start + chunk_chars, len(block))
            piece = block[start:end].strip()
            if piece:
                yield Chunk(
                    text=piece, doc_path=doc.rel_path, doc_name=doc.name,
                    position=position, page=page_index,
                    tokens_estimate=max(1, len(piece) // 4),
                )
                position += 1
            if end >= len(block):
                break
            start = max(start + 1, end - overlap)
