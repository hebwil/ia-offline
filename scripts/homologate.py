#!/usr/bin/env python3
"""Homologação real de uma plataforma — prova de inferência local.

Diferente do selftest (unitário) e do `doctor --informational` (diagnóstico),
este script EXIGE evidência de inferência real e falha se qualquer uma faltar:

  1. motor verificado e em execução
  2. chat não-stream com resposta não vazia
  3. streaming SSE com pelo menos um chunk
  4. RAG com citação de arquivo/página
  5. API HTTP local autorizada respondendo
  6. diagnóstico com todos os checks críticos OK
  7. encerramento seguro sem processos órfãos

Saída: logs/homologation-evidence.json + exit 0 somente se tudo passar.
"""

from __future__ import annotations

import base64
import json
import platform
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus3.server import NexusApp, run_server  # noqa: E402


def post(base: str, path: str, payload: dict, token: str, timeout: int = 180) -> dict:
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get(base: str, path: str, token: str) -> dict:
    request = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def check(name: str, ok: bool, evidence: dict, detail: str = "") -> None:
    evidence["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("  OK   " if ok else "  FALHA ") + name + (" — " + str(detail)[:160] if detail else ""))
    if not ok:
        evidence["failures"].append(name)


def main() -> int:
    evidence: dict = {
        "platform": {"system": platform.system(), "machine": platform.machine(), "release": platform.release()},
        "python": platform.python_version(),
        "checks": [], "failures": [], "timings_seconds": {},
    }
    app = NexusApp(root=ROOT, start_engine=True)
    status = app.status()
    engine = status["engine"]
    evidence["engine"] = {
        "key": engine.get("key"), "build": engine.get("build"),
        "installed": engine.get("installed"), "verification": engine.get("verification"),
        "archive_verified": engine.get("archive_verified"),
    }
    evidence["model"] = status.get("active_model")

    check("motor instalado e verificado", bool(engine.get("installed") and engine.get("archive_verified")),
          evidence, engine.get("verification", ""))
    check("motor em execução (processo gerenciado vivo)", bool(status["engine"].get("alive")),
          evidence, json.dumps(status.get("startup_errors", []), ensure_ascii=False))
    if evidence["failures"]:
        _write(evidence)
        return 1

    server = run_server(app, host="127.0.0.1", port=0)
    base = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        # API local autorizada
        health = get(base, "/health", app.api_key)
        check("API HTTP local responde", health.get("status") == "ok", evidence, json.dumps(health))

        # Chat real (não-stream)
        t0 = time.time()
        chat = post(base, "/api/chat", {
            "message": "Responda em uma frase curta: o que é um computador?"
        }, app.api_key)
        evidence["timings_seconds"]["chat"] = round(time.time() - t0, 2)
        reply = str(chat.get("reply", ""))
        check("inferência real não-stream (resposta não vazia)", len(reply.strip()) > 5, evidence, reply[:160])
        check("roteador anexou decisão explicável", bool(chat.get("route", {}).get("rationale")),
              evidence, chat.get("route", {}).get("model_id", ""))

        # Streaming SSE
        t0 = time.time()
        request = urllib.request.Request(
            base + "/api/chat_stream",
            data=json.dumps({"message": "Diga apenas: pronto"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {app.api_key}"},
            method="POST",
        )
        chunks = 0
        final = ""
        with urllib.request.urlopen(request, timeout=180) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if event.get("type") == "delta":
                    chunks += 1
                if event.get("type") == "done":
                    final = str(event.get("reply", ""))
                if event.get("type") == "close":
                    break
        evidence["timings_seconds"]["stream"] = round(time.time() - t0, 2)
        check("streaming SSE com chunks reais", chunks >= 1 and len(final.strip()) > 0,
              evidence, f"{chunks} chunks / final='{final[:60]}'")

        # RAG com citação real
        text = b"Clausula unica: o prazo para contestar e de 45 dias."
        upload = post(base, "/api/upload", {
            "name": "homologacao.txt", "kind": "text",
            "content": base64.b64encode(text).decode("ascii"),
        }, app.api_key)
        grounded = post(base, "/api/chat", {
            "message": "Qual o prazo para contestar segundo o documento? Cite a fonte."
        }, app.api_key)
        citations = [c.get("citation", "") for c in grounded.get("citations", [])]
        check("upload indexou documento", upload.get("ok") and upload.get("chunks", 0) >= 1,
              evidence, str(upload.get("chunks")))
        check("RAG citou arquivo e página reais",
              any("homologacao.txt" in c and "p. 1" in c for c in citations),
              evidence, json.dumps(citations, ensure_ascii=False))

        # Diagnóstico crítico
        doctor = get(base, "/api/doctor", app.api_key)
        critical = {"plataforma suportada", "raiz portátil", "motor instalado",
                    "motor em execução", "modelo de texto verificado"}
        failed = [c["name"] for c in doctor["checks"] if c["name"] in critical and not c["ok"]]
        check("diagnóstico: todos os checks críticos OK", not failed and doctor.get("ok"),
              evidence, json.dumps(failed))

        # Encerramento seguro
        stopped = app.engine.shutdown()
        remaining = app.engine.processes.snapshot()
        check("encerramento seguro sem processos órfãos", len(stopped) >= 1 and not remaining,
              evidence, f"parados={stopped} restantes={remaining}")
    finally:
        server.shutdown()
        server.server_close()

    evidence["result"] = "PASS" if not evidence["failures"] else "FAIL"
    _write(evidence)
    print("\nRESULTADO: " + evidence["result"])
    return 0 if evidence["result"] == "PASS" else 1


def _write(evidence: dict) -> None:
    out = ROOT / "logs" / "homologation-evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidência: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    raise SystemExit(main())
