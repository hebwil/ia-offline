"""Nexus Intelligent Router.

Escolhe modelo, agente, contexto, temperatura e orçamento com base em:
complexidade da solicitação, capacidade dos modelos instalados, hardware,
presença de documentos/imagens e necessidade de informação externa.

A decisão é sempre explicável: cada campo de `rationale` é exibido na UI.
Nunca anuncia capacidade que o modelo instalado não possui.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .agents import AGENTS, get_agent
from .config import Config
from .hardware import HardwareProfile, context_recommendation, gpu_layers_recommendation
from .models import ModelRegistry, ModelSpec, installation_status

_CODE_WORDS = re.compile(
    r"(?i)\b(c[oó]digo|script|python|javascript|typescript|powershell|bash|sql|bug|erro de compila"
    r"[çc][aã]o|fun[cç][aã]o|api|regex|debug|git|docker|html|css|json|lambda|classe)\b"
)
_LEGAL_WORDS = re.compile(
    r"(?i)\b(peti[cç][aã]o|recurso|impugna[cç][aã]o|manifestação|clt|cdc|cpc|c[có]digo civil|"
    r"jurisprud[eê]ncia|processo|senten[cç]a|advogad|jur[ií]dic|contrato|consumidor)\b"
)
_DATA_WORDS = re.compile(
    r"(?i)\b(csv|planilha|xlsx|tabela|m[eé]dia|soma|percentual|estat[ií]stica|gr[aá]fico|dados)\b"
)
_RESEARCH_WORDS = re.compile(
    r"(?i)\b(pesquis|not[ií]cias?|cota[cç][aã]o|d[oó]lar|pre[cç]o|hoje|atual|recente|"
    r"fonte|site|internet|web)\b"
)
_VISION_WORDS = re.compile(r"(?i)\b(imagem|print|foto|figura|screenshot|ocr|ler a imagem)\b")
_DOC_WORDS = re.compile(r"(?i)\b(anexo|documento|pdf|arquivo|contrato|relat[oó]rio)\b")
_COMPLEX_WORDS = re.compile(
    r"(?i)\b(analise|analisar|compare|comparar|detalh|profund|passo a passo|explique|justifique|"
    r"arquitetura|plano|estrat[eé]gia|configure|implemente)\b"
)


@dataclass
class Signal:
    message: str
    chars: int
    complexity: float  # 0..1
    needs_code: bool
    needs_legal: bool
    needs_data: bool
    needs_research: bool
    needs_vision: bool
    needs_docs: bool
    has_attachments: bool
    has_images: bool

    def required_capabilities(self) -> set[str]:
        caps = {"chat"}
        if self.needs_vision or self.has_images:
            caps.add("vision")
        elif self.needs_code:
            caps.add("code")
        return caps


@dataclass
class RouteDecision:
    model_id: str
    agent_id: str
    context: int
    gpu_layers: int
    temperature: float
    max_tokens: int
    needs_web: bool
    needs_documents: bool
    needs_vision: bool
    rationale: list[str] = field(default_factory=list)
    estimated_seconds: float = 0.0
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id, "agent_id": self.agent_id,
            "context": self.context, "gpu_layers": self.gpu_layers,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "needs_web": self.needs_web, "needs_documents": self.needs_documents,
            "needs_vision": self.needs_vision, "rationale": self.rationale,
            "estimated_seconds": round(self.estimated_seconds, 1),
            "fallback_used": self.fallback_used,
        }


def analyze(message: str, attachments: list[dict[str, Any]] | None = None) -> Signal:
    text = message or ""
    attachments = attachments or []
    has_images = any(
        str(a.get("kind", "")).startswith("image") or str(a.get("type", "")).startswith("image")
        for a in attachments
    )
    has_docs = any(
        str(a.get("kind", "")).lower() in ("pdf", "text", "docx", "xlsx", "csv")
        for a in attachments
    )
    matches = sum(bool(pattern.search(text)) for pattern in (
        _CODE_WORDS, _LEGAL_WORDS, _DATA_WORDS, _RESEARCH_WORDS, _COMPLEX_WORDS,
    ))
    length_factor = min(1.0, len(text) / 1800)
    complexity = min(1.0, 0.18 + length_factor * 0.42 + matches * 0.11 + (0.12 if has_docs else 0))
    return Signal(
        message=text, chars=len(text), complexity=round(complexity, 3),
        needs_code=bool(_CODE_WORDS.search(text)),
        needs_legal=bool(_LEGAL_WORDS.search(text)),
        needs_data=bool(_DATA_WORDS.search(text)),
        needs_research=bool(_RESEARCH_WORDS.search(text)),
        needs_vision=bool(_VISION_WORDS.search(text)),
        needs_docs=bool(_DOC_WORDS.search(text)) or has_docs,
        has_attachments=bool(attachments), has_images=has_images,
    )


def choose_agent(signal: Signal, requested: str = "automatico", online: bool = False) -> str:
    if requested and requested != "automatico" and requested in AGENTS:
        return requested
    if signal.needs_vision or signal.has_images:
        return "imagem"
    if signal.needs_legal:
        return "advogado"
    if signal.needs_code:
        return "programador"
    if signal.needs_data:
        return "analista"
    if signal.needs_research and online:
        return "pesquisador"
    return "geral"


class NexusRouter:
    def __init__(self, registry: ModelRegistry, hardware: HardwareProfile, config: Config):
        self.registry = registry
        self.hardware = hardware
        self.config = config

    def route(
        self,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        preferred_model: str = "",
        agent_id: str = "automatico",
        online: bool = False,
        doc_hits: int = 0,
    ) -> RouteDecision:
        signal = analyze(message, attachments)
        chosen_agent = choose_agent(signal, agent_id, online)
        rationale: list[str] = []
        rationale.append(
            f"Complexidade {signal.complexity:.2f} calculada por tamanho ({signal.chars} chars) "
            f"e {sum((signal.needs_code, signal.needs_legal, signal.needs_data, signal.needs_research))} sinais de domínio."
        )
        rationale.append(f"Agente '{chosen_agent}' selecionado para o tipo de tarefa.")

        installed_text = [
            spec for spec in self.registry.all()
            if spec.type == "text" and installation_status(self.registry.root, spec)[0]
        ]
        fallback = False
        if not installed_text:
            # Nada instalado: ainda devolvemos uma recomendação instalável.
            spec, reason = self.registry.select(
                self.hardware, {"chat"}, "text", preferred_model, installed_only=False
            )
            fallback = True
            rationale.append("Nenhum modelo de texto instalado; recomendação para instalação: " + reason)
            if spec is None:
                spec = self.registry.get("qwen3-0.6b-q8")
        else:
            pool = installed_text
            required = signal.required_capabilities()
            if "vision" in required:
                vision = [s for s in self.registry.all() if s.type == "vision"
                          and installation_status(self.registry.root, s)[0]]
                if vision:
                    spec = max(vision, key=lambda s: s.quality)
                    rationale.append("Modelo de visão instalado escolhido para imagem anexada.")
                else:
                    rationale.append("Imagem detectada, mas nenhum modelo de visão instalado; visão não será simulada.")
                    required = {"chat"}
            spec, reason = self.registry.select(
                self.hardware, required, "text", preferred_model,
                installed_only=True,
            )
            if spec is None and required != {"chat"}:
                spec, reason = self.registry.select(
                    self.hardware, {"chat"}, "text", preferred_model, installed_only=True
                )
                rationale.append("Capacidade especializada indisponível; degradado para modelo de texto: " + reason)
            if spec is None:
                spec = pool[0]
                rationale.append("Fallback para o único modelo de texto instalado.")
            rationale.append("Seleção: " + reason)

        spec = spec or self.registry.get("qwen3-4b-q4")
        model_id = spec.id if spec else "unknown"

        ctx = context_recommendation(self.hardware, spec.max_ctx if spec else 4096)
        if signal.needs_docs or doc_hits:
            ctx = min(spec.max_ctx if spec else 8192, max(ctx, 8192))
            rationale.append("Contexto ampliado para 8192 tokens por presença de documentos.")
        gpu_layers = gpu_layers_recommendation(self.hardware)
        rationale.append(
            f"Hardware {self.hardware.tier} com {self.hardware.ram_total_gb:.1f} GB RAM e "
            f"{self.hardware.vram_total_gb:.1f} GB VRAM → contexto {ctx}, gpu_layers {gpu_layers}."
        )

        temperature = 0.7
        if signal.needs_code or signal.needs_legal or signal.needs_data:
            temperature = 0.25
        elif signal.needs_research:
            temperature = 0.45
        rationale.append(f"Temperatura {temperature} conforme tipo de tarefa.")

        max_tokens = 768
        if signal.complexity > 0.7:
            max_tokens = 1536
        if signal.needs_code:
            max_tokens = 2048

        size_gb = spec.size_gb if spec else 2.5
        effective_gb = min(size_gb, self.hardware.vram_total_gb or size_gb)
        throughput = 6.0 if self.hardware.vram_total_gb >= 4 else 1.6
        estimated = 3 + (max_tokens / throughput) + (signal.chars / 900)

        return RouteDecision(
            model_id=model_id,
            agent_id=chosen_agent,
            context=ctx,
            gpu_layers=gpu_layers,
            temperature=temperature,
            max_tokens=max_tokens,
            needs_web=bool(online and signal.needs_research),
            needs_documents=bool(signal.needs_docs or doc_hits),
            needs_vision=bool(signal.needs_vision or signal.has_images),
            rationale=rationale,
            estimated_seconds=estimated,
            fallback_used=fallback,
        )
