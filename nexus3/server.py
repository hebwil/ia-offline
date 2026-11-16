"""Servidor HTTP local: API da aplicação, API compatível com OpenAI e UI.

Escuta apenas em 127.0.0.1. Nenhum endpoint executa comandos do host.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import threading
import time
import urllib.parse
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from .agents import get_agent, list_agents
from .chat import ChatStore
from .config import Config, environment_summary, install_id
from .documents import DocumentError, DocumentExtractor
from .engine import EngineError, EngineManager
from .hardware import detect_hardware
from .models import DownloadManager, ModelRegistry, installation_status
from .platform import PlatformInfo, detect_platform, find_root
from .rag import DocumentStore
from .router import NexusRouter, RouteDecision
from .security import PathGuard, ProcessRegistry, redact
from .tools import ToolRuntime
from .web import WebSearch, WebSearchDisabled

SYSTEM_IDENTITY = (
    "Você é o WillTechBH IA Nexus Portable 3.0, assistente local e portátil. "
    "Responda sempre em português do Brasil. O computador hospedeiro empresta hardware; "
    "o projeto guarda dados, histórico e configuração na própria pasta portátil. "
    "Use caminhos relativos à raiz do projeto. Não afirme ter acesso a recursos que não foram fornecidos. "
    "Distinga claramente fatos extraídos de documentos, informações externas coletadas e inferências suas."
)

MAX_BODY = 60 * 1024 * 1024


class NexusApp:
    """Estado da aplicação, independente do protocolo HTTP."""

    def __init__(self, root: Path | None = None, start_engine: bool = True):
        self.root = (Path(root) if root else find_root()).resolve()
        self.platform_info: PlatformInfo = detect_platform()
        self.config = Config.load(self.root)
        self.guard = PathGuard(self.root)
        self.hardware = detect_hardware(self.platform_info, self.root, self.config)
        self.registry = ModelRegistry(self.root)
        self.engine = EngineManager(self.root, self.platform_info, self.hardware, self.config)
        self.router = NexusRouter(self.registry, self.hardware, self.config)
        self.extractor = DocumentExtractor(self.root)
        self.store = DocumentStore(self.root, self.config, embed_fn=self._embed)
        self.chat = ChatStore(self.root)
        self.tools = ToolRuntime(self.config, self.store)
        self.downloads = DownloadManager(self.root, self.config)
        self.web = WebSearch(enabled=False)
        self.installation_id = install_id(self.root)
        self.mode = "offline"
        # Chave da API/engine e token da sessão HTTP são deliberadamente distintos:
        # o navegador recebe apenas o token da sessão via cookie HttpOnly.
        self.api_key = self._api_key()
        self.session_token = uuid.uuid4().hex
        self.download_authorization = False
        self.last_route: RouteDecision | None = None
        self.lock = threading.RLock()
        self.start_engine = start_engine
        self.startup_errors: list[str] = []
        if start_engine:
            self._auto_start()

    # --------------------------------------------------------------- setup

    def _api_key(self) -> str:
        configured = str(self.config.get("server.api_key") or "").strip()
        if configured:
            return configured
        env_key = os.environ.get("NEXUS3_API_KEY")
        if env_key:
            return env_key
        return uuid.uuid4().hex

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self.config.get("rag.use_embeddings") or not self.engine.running:
            raise RuntimeError("Embeddings não habilitados.")
        return self.engine.embeddings(texts, self.api_key)

    def _auto_start(self) -> None:
        installed = [
            spec for spec in self.registry.all()
            if spec.type == "text" and installation_status(self.root, spec)[0]
        ]
        if not installed:
            self.startup_errors.append(
                "Nenhum modelo de texto instalado. Use 'nexus3.py models install <id> --yes' ou "
                "o gerenciador na interface. A interface permanece disponível para diagnóstico."
            )
            return
        preferred = str(self.config.get("engine.preferred_model") or "")
        spec = self.registry.get(preferred) if preferred else None
        spec = spec if spec and installation_status(self.root, spec)[0] else max(
            installed, key=lambda s: (s.priority, -s.size_gb)
        )
        files = [self.guard.resolve(*item.path.split("/")) for item in spec.files]
        try:
            self.engine.start(
                spec=spec, model_file=files[0],
                context=min(8192, spec.max_ctx),
                gpu_layers=0,
                api_key=self.api_key,
            )
            self.config.set("engine.preferred_model", spec.id)
            self.config.save()
        except (EngineError, PermissionError, OSError, Exception) as exc:
            self.startup_errors.append(redact(f"Falha ao iniciar motor: {type(exc).__name__}: {exc}"))

    # -------------------------------------------------------------- status

    def status(self) -> dict[str, Any]:
        engine_status = self.engine.status()
        return {
            "ok": True,
            "version": __version__,
            "product": self.config.get("product_name"),
            "mode": self.mode,
            "platform": {
                "system": self.platform_info.system,
                "arch": self.platform_info.arch,
                "python": self.platform_info.python,
            },
            "hardware": self.hardware.to_dict(),
            "engine": engine_status,
            "active_model": self.config.get("engine.preferred_model", ""),
            "models_installed": [
                spec.id for spec in self.registry.all()
                if installation_status(self.root, spec)[0]
            ],
            "documents": len(self.store.list_documents()),
            "chunks": len(self.store.chunks),
            "tools_enabled": self.tools.enabled,
            # Indica apenas que o modo online não foi proibido por política/ambiente;
            # não afirma que existe conectividade real neste instante.
            "online_available": not bool(os.environ.get("NEXUS3_OFFLINE")),
            "online_active": self.web.enabled,
            "installation_id": self.installation_id,
            "startup_errors": self.startup_errors,
            "route": self.last_route.to_dict() if self.last_route else None,
        }

    SETTINGS_PATHS: dict[str, tuple[Any, Any]] = {
        # path -> (validator, UISchema hint). Apenas chaves seguras e locais.
        "defaults.temperature": (float, "0..1"),
        "defaults.max_tokens": (int, "64..8192"),
        "defaults.context_strategy": (str, "auto|compact|full"),
        "rag.top_k": (int, "1..20"),
        "rag.use_embeddings": (bool, "boolean"),
        "engine.request_timeout_seconds": (int, "10..600"),
        "engine.idle_sleep_seconds": (int, "0..3600"),
        "privacy.send_documents_externally": (bool, "boolean"),
    }

    def settings_view(self) -> dict[str, Any]:
        return {path: self.config.get(path) for path in self.SETTINGS_PATHS}

    def update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        updated: dict[str, Any] = {}
        for path, raw in (values or {}).items():
            if path not in self.SETTINGS_PATHS:
                raise ValueError(f"Configuração não ajustável pela interface: {path}")
            caster, _ = self.SETTINGS_PATHS[path]
            if caster is bool:
                value = bool(raw)
            else:
                value = caster(raw)
            if path == "defaults.temperature" and not 0.0 <= float(value) <= 1.0:
                raise ValueError("Temperatura deve estar entre 0 e 1.")
            if path == "defaults.max_tokens" and not 64 <= int(value) <= 8192:
                raise ValueError("max_tokens deve estar entre 64 e 8192.")
            if path == "defaults.context_strategy" and value not in ("auto", "compact", "full"):
                raise ValueError("Estratégia de contexto inválida.")
            if path == "rag.top_k" and not 1 <= int(value) <= 20:
                raise ValueError("top_k deve estar entre 1 e 20.")
            if path == "engine.request_timeout_seconds" and not 10 <= int(value) <= 600:
                raise ValueError("Timeout deve estar entre 10 e 600 segundos.")
            if path == "engine.idle_sleep_seconds" and not 0 <= int(value) <= 3600:
                raise ValueError("Idle deve estar entre 0 e 3600 segundos.")
            self.config.set(path, value)
            updated[path] = value
        if updated:
            self.config.save()
        return {"ok": True, "updated": updated, "settings": self.settings_view()}

    def set_online(self, enabled: bool) -> dict[str, Any]:
        enabled = bool(enabled)
        if enabled and os.environ.get("NEXUS3_OFFLINE"):
            raise PermissionError("Modo online foi desativado pelo ambiente (NEXUS3_OFFLINE).")
        with self.lock:
            self.web.enabled = enabled
            self.mode = "online" if enabled else "offline"
        return {
            "ok": True, "online_active": enabled,
            "opt_in_required": bool(self.config.get("privacy.online_opt_in_required")),
            "documents_externally": bool(self.config.get("privacy.send_documents_externally")),
        }

    def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "ok": ok, "detail": redact(detail)})

        add("plataforma suportada", self.platform_info.engine_key in (
            "win-cpu-x64", "win-cpu-arm64", "macos-arm64", "macos-x64", "ubuntu-x64", "ubuntu-arm64"
        ), self.platform_info.engine_key)
        add("raiz portátil", self.root.exists(), str(self.root.name))
        engine_info = self.engine.engine_info()
        add("motor instalado", engine_info["installed"], engine_info["binary"] or "ausente")
        engine_alive = bool(self.engine.running and self.engine.status().get("alive"))
        add("motor em execução", engine_alive, "sim" if engine_alive else "não")
        installed = [
            spec for spec in self.registry.all()
            if spec.type == "text" and installation_status(self.root, spec)[0]
        ]
        add("modelo de texto verificado", bool(installed), ", ".join(s.id for s in installed) or "nenhum")
        add("documentos indexados", bool(self.store.documents), f"{len(self.store.documents)} documento(s)")
        add("OCR local", bool(__import__("shutil").which("tesseract")), "tesseract no PATH" if __import__("shutil").which("tesseract") else "não disponível")
        add("modo online", self.web.enabled, "ativado apenas por solicitação" if self.web.enabled else "desativado (padrão)")
        # doctor.ok agora significa "pronto para uso", não apenas "era portátil".
        # Diagnósticos opcionais (OCR, documentos, modo online) continuam visíveis
        # mas não mascaram a ausência de motor ou modelo.
        critical = {
            "plataforma suportada", "raiz portátil", "motor instalado",
            "motor em execução", "modelo de texto verificado",
        }
        return {
            "ok": all(c["ok"] for c in checks if c["name"] in critical),
            "checks": checks,
            "warnings": self.hardware.warnings,
        }

    # ------------------------------------------------------------- modelos

    def models(self) -> list[dict[str, Any]]:
        return [spec.to_public_dict(self.root) for spec in self.registry.all()]

    def authorize_downloads(self, allow: bool) -> dict[str, Any]:
        """Autorização volátil da UI: vale para uma operação, nunca é persistida."""
        self.download_authorization = bool(allow)
        return {"ok": True, "allowed": self.download_authorization, "persistent": False}

    def install_model(self, model_id: str, callback=None) -> dict[str, Any]:
        spec = self.registry.get(model_id)
        if not spec:
            raise ValueError(f"Modelo desconhecido: {model_id}")
        persistent = bool(self.config.get("downloads.allow_external"))
        if not persistent and not self.download_authorization:
            raise PermissionError(
                "Downloads externos exigem autorização explícita nesta sessão."
            )
        try:
            paths = self.downloads.ensure_model(spec, callback)
        finally:
            # Autorização da UI é consumida mesmo em falha/cancelamento.
            self.download_authorization = False
        return {"ok": True, "id": model_id, "files": [str(p.relative_to(self.root)) for p in paths]}

    def cancel_download(self, key: str = "*") -> dict[str, Any]:
        self.downloads.cancel(key or "*")
        return {"ok": True, "cancelled": key or "*"}

    def select_model(self, model_id: str) -> dict[str, Any]:
        spec = self.registry.get(model_id)
        if not spec:
            raise ValueError(f"Modelo desconhecido: {model_id}")
        ok, verified = installation_status(self.root, spec)
        if not ok:
            raise ValueError(f"Modelo {model_id} não está instalado.")
        if not verified:
            raise ValueError(f"Modelo {model_id} falhou na verificação de hash.")
        files = [self.guard.resolve(*item.path.split("/")) for item in spec.files]
        mmproj = files[1] if spec.type == "vision" and len(files) > 1 else None
        was_running = bool(self.engine.running)
        if was_running:
            self.engine.stop()
        self.engine.start(
            spec=spec, model_file=files[0],
            context=min(spec.max_ctx, 8192),
            gpu_layers=0,
            api_key=self.api_key,
            mmproj=mmproj,
        )
        self.config.set("engine.preferred_model", model_id)
        self.config.save()
        return {"ok": True, "model_id": model_id, "swapped": was_running}

    def _ensure_runtime_model(self, route: RouteDecision) -> None:
        """Carrega o modelo escolhido pelo Router antes da inferência.

        v3.0 inicial calculava gpu_layers no Router e passava 0 ao engine; além
        disso, uma decisão de visão nunca trocava o modelo/texto carregado.
        """
        spec = self.registry.get(route.model_id)
        if not spec:
            raise EngineError(f"Modelo roteado não existe no registro: {route.model_id}")
        present, verified = installation_status(self.root, spec)
        if not present or not verified:
            raise EngineError(
                f"Modelo {spec.id} não está instalado ou falhou na verificação de hash."
            )

        files = [self.guard.resolve(*item.path.split("/")) for item in spec.files]
        if route.vision_model_id:
            if spec.type != "vision" or spec.id != route.vision_model_id:
                raise EngineError("Decisão de visão inconsistente: modelo verificado diferente do roteado.")
            if len(files) < 2 or not files[1].is_file():
                raise EngineError("Modelo de visão incompleto: arquivo mmproj ausente.")
            mmproj = files[1]
        else:
            mmproj = None

        running = self.engine.running
        if running and running.model_id == spec.id:
            return
        if running:
            self.engine.stop()
        self.engine.start(
            spec=spec,
            model_file=files[0],
            context=max(1024, route.context),
            gpu_layers=max(0, route.gpu_layers),
            api_key=self.api_key,
            mmproj=mmproj,
        )
        self.config.set("engine.preferred_model", spec.id)
        self.config.save()

    # ------------------------------------------------------------ uploads

    def upload(self, name: str, kind: str, content: str) -> dict[str, Any]:
        safe_name = Path(name or "arquivo").name[:120]
        if not safe_name or safe_name in (".", ".."):
            raise ValueError("Nome de arquivo inválido.")
        destination = self.guard.resolve("workspace", "uploads", safe_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if "," in content and content.strip().startswith("data:"):
            content = content.split(",", 1)[1]
        try:
            raw = base64.b64decode(content, validate=False)
        except Exception as exc:
            raise ValueError(f"Conteúdo base64 inválido: {type(exc).__name__}") from exc
        if len(raw) > 25 * 1024 * 1024:
            raise ValueError("Arquivo acima do limite de 25 MB.")
        destination.write_bytes(raw)
        rel = str(destination.relative_to(self.root))
        result: dict[str, Any] = {
            "ok": True, "name": safe_name, "kind": kind, "path": rel, "size": len(raw),
        }
        if kind in ("text", "pdf", "docx", "xlsx", "csv", "image"):
            try:
                doc = self.extractor.extract(destination, rel)
                pieces = self.store.index_document(doc)
                result.update({
                    "extracted_chars": len(doc.text), "chunks": pieces,
                    "warnings": doc.warnings, "preview": doc.text[:300],
                })
            except DocumentError as exc:
                result["warnings"] = [str(exc)]
        return result

    # --------------------------------------------------------------- chat

    def _messages(
        self, message: str, route: RouteDecision, attachments: list[dict[str, Any]], doc_results: list
    ) -> list[dict[str, Any]]:
        agent = get_agent(route.agent_id)
        system_parts = [SYSTEM_IDENTITY]
        if agent.prompt:
            system_parts.append(agent.prompt)
        if doc_results:
            system_parts.append(self.store.grounded_prompt(message, doc_results, ""))
        if route.needs_web and self.web.enabled:
            try:
                system_parts.append(WebSearch.context(self.web.search(message)))
            except (WebSearchDisabled, Exception) as exc:
                system_parts.append(f"Busca externa falhou: {type(exc).__name__}. Continue localmente.")
        if attachments:
            summaries = []
            for item in attachments:
                summaries.append(
                    f"- {item.get('name', 'arquivo')} ({item.get('kind', 'text')}): "
                    f"{str(item.get('preview', ''))[:400]}"
                )
            system_parts.append("ANEXOS DO USUÁRIO (conteúdo já extraído e indexado):\n" + "\n".join(summaries))
        messages: list[dict[str, Any]] = [{"role": "system", "content": "\n\n".join(system_parts)}]
        for row in self.chat.load(self.chat.active)[-12:]:
            if row.get("role") in ("user", "assistant") and row.get("content"):
                messages.append({"role": row["role"], "content": str(row["content"])[:6000]})
        messages.append({"role": "user", "content": self._user_content(message, attachments, route)})
        return messages

    @staticmethod
    def _user_content(
        message: str, attachments: list[dict[str, Any]], route: RouteDecision
    ) -> str | list[dict[str, Any]]:
        """Envia bytes de imagem ao modelo de visão, nunca apenas um resumo textual."""
        if not (route.vision_model_id and route.has_image_input):
            return message
        parts: list[dict[str, Any]] = [{"type": "text", "text": message}]
        for item in attachments:
            kind = str(item.get("kind", ""))
            payload = str(item.get("content", ""))
            if not kind.startswith("image") or not payload.startswith("data:image/"):
                continue
            if "," not in payload:
                continue
            header, encoded = payload.split(",", 1)
            if ";base64" not in header or not encoded:
                continue
            parts.append({
                "type": "image_url",
                "image_url": {"url": payload},
            })
        if len(parts) == 1:
            raise EngineError(
                "Anexo de imagem sem bytes utilizáveis. Reenvie o arquivo; visão não será simulada."
            )
        return parts

    def prepare(self, message: str, attachments: list[dict[str, Any]], agent_id: str,
                model_id: str, online: bool) -> tuple[RouteDecision, list[dict[str, Any]], list]:
        if not message.strip():
            raise ValueError("Mensagem vazia.")
        # O parâmetro `online` é o opt-in explícito (UI ou cliente da API).
        # A versão anterior usava `online AND online_opt_in_required`, o que
        # desativava o modo online justamente quando a política exigia opt-in.
        self.web.enabled = bool(online) and not bool(os.environ.get("NEXUS3_OFFLINE"))
        doc_results = self.store.search(message) if self.store.chunks else []
        route = self.router.route(
            message, attachments, preferred_model=model_id,
            agent_id=agent_id, online=self.web.enabled, doc_hits=len(doc_results),
        )
        with self.lock:
            self.last_route = route
            self.mode = "online" if self.web.enabled else "offline"
        if route.has_image_input and not route.vision_model_id:
            raise EngineError(
                "Imagem anexada detectada, mas nenhum modelo de visão verificado e compatível está instalado. "
                "Instale um modelo de visão para esta tarefa; não vamos fingir que houve análise visual."
            )
        self._ensure_runtime_model(route)
        return route, self._messages(message, route, attachments, doc_results), doc_results

    def chat_once(
        self, message: str, attachments: list[dict[str, Any]] | None = None,
        agent_id: str = "automatico", model_id: str = "", online: bool = False,
    ) -> dict[str, Any]:
        attachments = attachments or []
        route, messages, doc_results = self.prepare(message, attachments, agent_id, model_id, online)
        if not self.engine.running:
            raise EngineError("Motor local não está em execução. Verifique 'nexus3.py doctor'.")
        payload = {
            "model": route.model_id,
            "messages": messages,
            "temperature": route.temperature,
            "max_tokens": route.max_tokens,
        }
        response = self.engine.chat(payload, self.api_key)
        reply = ""
        try:
            reply = response["choices"][0]["message"].get("content", "")
        except (KeyError, IndexError, TypeError):
            reply = json.dumps(response, ensure_ascii=False)[:1200]
        source = "local"
        if doc_results:
            source += "+documentos"
        if route.needs_web and self.web.enabled:
            source += "+web"
        self.chat.append("user", message, source="user")
        self.chat.append("assistant", reply, source=source, route=route.to_dict())
        return {
            "ok": True, "reply": reply, "source": source,
            "route": route.to_dict(),
            "citations": [r.to_dict() for r in doc_results],
        }

    def chat_stream(
        self, message: str, attachments: list[dict[str, Any]] | None = None,
        agent_id: str = "automatico", model_id: str = "", online: bool = False,
    ) -> Iterator[dict[str, Any]]:
        attachments = attachments or []
        route, messages, doc_results = self.prepare(message, attachments, agent_id, model_id, online)
        yield {"type": "status", "text": f"Roteador: {route.agent_id} · {route.model_id} · {route.context} tokens"}
        if not self.engine.running:
            yield {"type": "error", "error": "Motor local não está em execução."}
            return
        payload = {
            "model": route.model_id, "messages": messages,
            "temperature": route.temperature, "max_tokens": route.max_tokens,
        }
        collected: list[str] = []
        try:
            for chunk in self.engine.stream_chat(payload, self.api_key):
                if chunk.get("type") == "done":
                    break
                try:
                    delta = chunk["choices"][0].get("delta", {}).get("content", "")
                except (KeyError, IndexError, TypeError):
                    delta = ""
                if delta:
                    collected.append(delta)
                    yield {"type": "delta", "text": delta}
        except Exception as exc:
            yield {"type": "error", "error": redact(f"Falha na inferência: {type(exc).__name__}: {exc}")}
            return
        reply = "".join(collected)
        source = "local"
        if doc_results:
            source += "+documentos"
        if route.needs_web and self.web.enabled:
            source += "+web"
        self.chat.append("user", message, source="user")
        self.chat.append("assistant", reply, source=source, route=route.to_dict())
        yield {
            "type": "done", "reply": reply, "source": source,
            "route": route.to_dict(), "citations": [r.to_dict() for r in doc_results],
        }

    # ------------------------------------------------------ compat OpenAI

    def openai_chat(self, payload: dict[str, Any], stream: bool) -> dict[str, Any] | Iterator[dict[str, Any]]:
        messages = payload.get("messages") or []
        if not messages:
            raise ValueError("messages é obrigatório.")
        user_text = "\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "user"
        ) or str(messages[-1].get("content", ""))
        route, full_messages, docs = self.prepare(
            user_text, [], "automatico", str(payload.get("model") or ""), False
        )
        forwarded = {
            "model": route.model_id, "messages": full_messages,
            "temperature": float(payload.get("temperature", route.temperature)),
            "max_tokens": int(payload.get("max_tokens", route.max_tokens)),
        }
        if stream:
            return self.engine.stream_chat(forwarded, self.api_key)
        return self.engine.chat(forwarded, self.api_key)


class NexusHTTPHandler(BaseHTTPRequestHandler):
    server_version = "Nexus3/3.0"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> NexusApp:
        return self.server.app  # type: ignore[attr-defined,no-any-return]

    # ------------------------------------------------------------ helpers

    def _json(self, obj: Any, status: int = 200) -> None:
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.end_headers()
        self.wfile.write(payload)

    def _sse(self, event: dict[str, Any]) -> None:
        payload = ("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8")
        self.wfile.write(payload)
        self.wfile.flush()

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("Corpo da requisição muito grande.")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _cookies(self) -> SimpleCookie:
        jar: SimpleCookie = SimpleCookie()
        raw = self.headers.get("Cookie", "")
        if raw:
            try:
                jar.load(raw)
            except Exception:
                pass
        return jar

    def _authorized(self) -> bool:
        if not getattr(self.server, "require_auth", False):
            return True
        header = self.headers.get("Authorization", "").strip()
        if header and header == f"Bearer {self.app.api_key}":
            return True
        configured = str(self.app.config.get("server.api_key") or "").strip()
        if configured and header == f"Bearer {configured}":
            return True
        session = self._cookies().get("nexus3_session")
        return bool(session and session.value == self.app.session_token)

    def _ensure_session_cookie(self) -> None:
        """Emite cookie HttpOnly somente para a UI local, nunca a chave da engine."""
        session = self._cookies().get("nexus3_session")
        if session and session.value == self.app.session_token:
            return
        self.send_header(
            "Set-Cookie",
            f"nexus3_session={self.app.session_token}; Path=/; HttpOnly; SameSite=Strict",
        )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------------------------------------------------------------- GET

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            is_api = path.startswith("/api/") or path.startswith("/v1/") or path == "/health"
            public_api = path in ("/health", "/v1/health")
            if is_api and not public_api and not self._authorized():
                self._json({"ok": False, "error": "Não autorizado."}, 401)
                return
            if path == "/health":
                self._json({"status": "ok", "version": __version__})
                return
            if path == "/v1/health":
                self._json({"status": "ok"})
                return
            if path == "/v1/models":
                model_id = self.app.config.get("engine.preferred_model") or "nexus-local"
                self._json({
                    "object": "list",
                    "data": [{"id": model_id, "object": "model", "owned_by": "local", "created": int(time.time())}],
                })
                return
            if path == "/api/status":
                self._json(self.app.status())
                return
            if path == "/api/settings":
                self._json({"ok": True, "settings": self.app.settings_view()})
                return
            if path == "/api/doctor":
                self._json(self.app.doctor())
                return
            if path == "/api/models":
                self._json({"ok": True, "models": self.app.models()})
                return
            if path == "/api/agents":
                self._json({"ok": True, "agents": list_agents()})
                return
            if path == "/api/tools":
                self._json({
                    "ok": True,
                    "enabled": self.app.tools.enabled,
                    "definitions": self.app.tools.definitions(),
                })
                return
            if path == "/api/docs":
                self._json({"ok": True, "documents": self.app.store.list_documents()})
                return
            if path == "/api/docs/search":
                query = (qs.get("q") or [""])[0]
                self._json({"ok": True, "results": [r.to_dict() for r in self.app.store.search(query)]})
                return
            if path == "/api/history":
                self._json({"ok": True, "active": self.app.chat.active, "chats": self.app.chat.list()})
                return
            if path == "/api/history/search":
                term = (qs.get("q") or [""])[0]
                self._json({"ok": True, "active": self.app.chat.active, "chats": self.app.chat.search(term)})
                return
            if path == "/api/history/load":
                sid = (qs.get("id") or [""])[0]
                if not sid or not self.app.chat.path(sid).exists():
                    self._json({"ok": False, "error": "Conversa não encontrada."}, 404)
                    return
                self.app.chat.active = sid
                self._json({"ok": True, "active": sid, "messages": self.app.chat.load(sid)})
                return
            self._serve_static(path)
        except Exception as exc:
            self._json({"ok": False, "error": redact(f"{type(exc).__name__}: {exc}")}, 500)

    def _serve_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        rel = urllib.parse.unquote(path).lstrip("/").replace("\\", "/")
        if ".." in rel.split("/") or rel.startswith("/"):
            self.send_error(403)
            return
        target = self.app.guard.resolve("nexus3", "ui", *rel.split("/"))
        if not target.is_file():
            self.send_error(404)
            return
        content = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".css", ".html"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self._ensure_session_cookie()
        self.end_headers()
        self.wfile.write(content)

    # --------------------------------------------------------------- POST

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            if not self._authorized():
                self._json({"ok": False, "error": "Não autorizado."}, 401)
                return
            body = self._body()

            if path == "/api/settings":
                self._json(self.app.update_settings(body.get("values", body)))
                return

            if path == "/api/online":
                self._json(self.app.set_online(body.get("enabled", False)))
                return

            if path == "/api/tools/call":
                if self.app.config.get("tools.require_confirmation", True) and not body.get("confirm"):
                    raise PermissionError("Confirme explicitamente a execução da ferramenta.")
                result = self.app.tools.call(
                    str(body.get("name", "")), body.get("arguments") or {}
                )
                self._json({"ok": True, "name": body.get("name"), "result": result})
                return

            if path == "/api/chat":
                self._json(self.app.chat_once(
                    body.get("message", ""), body.get("attachments", []),
                    body.get("agent", "automatico"), body.get("model", ""),
                    bool(body.get("online")),
                ))
                return

            if path == "/api/chat_stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
                self.close_connection = True
                self.end_headers()
                for event in self.app.chat_stream(
                    body.get("message", ""), body.get("attachments", []),
                    body.get("agent", "automatico"), body.get("model", ""),
                    bool(body.get("online")),
                ):
                    self._sse(event)
                self._sse({"type": "close"})
                return

            if path == "/api/upload":
                self._json(self.app.upload(
                    body.get("name", ""), body.get("kind", "text"), body.get("content", "")
                ))
                return

            if path == "/api/models/install":
                self._json(self.app.install_model(str(body.get("id", ""))))
                return

            if path == "/api/models/select":
                self._json(self.app.select_model(str(body.get("id", ""))))
                return

            if path == "/api/models/authorize":
                self._json(self.app.authorize_downloads(bool(body.get("allow"))))
                return

            if path == "/api/models/cancel":
                self._json(self.app.cancel_download(str(body.get("key") or "*")))
                return

            if path == "/api/new_chat":
                self._json({"ok": True, "active": self.app.chat.new()})
                return

            if path == "/api/clear":
                self.app.chat.clear()
                self._json({"ok": True})
                return

            if path == "/api/history/delete":
                self._json({"ok": self.app.chat.delete(str(body.get("id", "")))})
                return

            if path == "/api/docs/index":
                doc = self.app.extractor.extract_path(str(body.get("path", "")))
                self._json({"ok": True, "chunks": self.app.store.index_document(doc), "document": doc.to_dict()})
                return

            if path == "/api/docs/clear":
                self.app.store.clear()
                self._json({"ok": True})
                return

            if path == "/api/stop":
                self._json({"ok": self.app.engine.stop()})
                return

            if path == "/api/shutdown":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            if path == "/v1/chat/completions":
                result = self.app.openai_chat(body, bool(body.get("stream")))
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.close_connection = True
                    self.end_headers()
                    for chunk in result:
                        self._sse(chunk if isinstance(chunk, dict) else {"type": "error", "error": "formato inválido"})
                    self._sse({"type": "done"})
                    return
                self._json(result)
                return

            self._json({"ok": False, "error": "Endpoint não encontrado."}, 404)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
        except PermissionError as exc:
            self._json({"ok": False, "error": str(exc)}, 403)
        except EngineError as exc:
            self._json({"ok": False, "error": redact(str(exc)), "engine_dead": True}, 503)
        except Exception as exc:
            self._json({"ok": False, "error": redact(f"{type(exc).__name__}: {exc}")}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("NEXUS3_VERBOSE"):
            print("[http]", redact(fmt % args), flush=True)


def run_server(app: NexusApp, host: str = "127.0.0.1", port: int = 0, require_auth: bool = True) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise PermissionError("Por política, o servidor Nexus só pode escutar em loopback.")
    if require_auth and not app.api_key and not app.session_token:
        raise PermissionError("Autenticação local não pode ser desativada sem credencial.")

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    server = Server((host, port), NexusHTTPHandler)
    server.app = app  # type: ignore[attr-defined]
    server.require_auth = require_auth  # type: ignore[attr-defined]
    return server
