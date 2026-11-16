#!/usr/bin/env python3
"""Smoke test ponta a ponta com motor e modelo reais.

Executa: inicialização → status → chat não-stream → chat stream → upload
de documento → pergunta fundamentada → diagnóstico → encerramento seguro.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus3.server import NexusApp, run_server  # noqa: E402


def post(base: str, path: str, payload: dict, token: str) -> dict:
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def get(base: str, path: str, token: str) -> dict:
    request = urllib.request.Request(
        base + path, headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    app = NexusApp(root=root, start_engine=True)
    print("== STATUS INICIAL ==")
    status = app.status()
    print(json.dumps({
        "plataforma": status["platform"],
        "hardware": {k: status["hardware"][k] for k in ("tier", "ram_total_gb", "cpu_model", "filesystem")},
        "engine": status["engine"],
        "startup_errors": status["startup_errors"],
    }, ensure_ascii=False, indent=2, default=str))
    if not status["engine"]["alive"]:
        print("FALHA: motor não iniciou.")
        return 1

    server = run_server(app, port=0)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"\nServidor de teste em {base}")

    print("\n== CHAT SIMPLES (não-stream) ==")
    started = time.time()
    result = post(base, "/api/chat", {"message": "Responda em uma frase: o que é o Nexus Portable?"}, app.api_key)
    print("reply:", result.get("reply", "")[:500].replace("\n", " "))
    print("source:", result.get("source"))
    print("route:", {k: result.get("route", {}).get(k) for k in ("model_id", "agent_id", "context", "temperature")})
    print("tempo: %.1fs" % (time.time() - started))

    print("\n== CHAT STREAM (SSE) ==")
    started = time.time()
    request = urllib.request.Request(
        base + "/api/chat_stream",
        data=json.dumps({"message": "Diga 'pronto' em português."}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {app.api_key}",
        }, method="POST",
    )
    chunks = 0
    done = None
    with urllib.request.urlopen(request, timeout=180) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            if event.get("type") == "delta":
                chunks += 1
            if event.get("type") == "done":
                done = event
            if event.get("type") == "close":
                break
    print("chunks recebidos:", chunks)
    print("resposta final:", (done or {}).get("reply", "")[:200].replace("\n", " "))
    print("tempo: %.1fs" % (time.time() - started))

    print("\n== DOCUMENTO + RAG ==")
    text = ("Clausula unica: o prazo para contestar e de 45 dias. "
            "A multa por atraso e de 2 por cento ao mes.").encode("utf-8")
    upload = post(base, "/api/upload", {
        "name": "contrato-teste.txt", "kind": "text",
        "content": base64.b64encode(text).decode("ascii"),
    }, app.api_key)
    print("upload:", {k: upload.get(k) for k in ("ok", "chunks", "size")})
    grounded = post(base, "/api/chat", {
        "message": "Qual o prazo para contestar segundo o documento anexado? Cite a fonte."
    }, app.api_key)
    print("reply:", grounded.get("reply", "")[:600].replace("\n", " "))
    print("source:", grounded.get("source"))
    print("citacoes:", [c.get("citation") for c in grounded.get("citations", [])])

    print("\n== DIAGNOSTICO ==")
    doctor = get(base, "/api/doctor", app.api_key)
    for check in doctor["checks"]:
        print(" ", "OK " if check["ok"] else "NAO", check["name"], "-", check["detail"][:90])
    print("warnings:", doctor["warnings"])

    print("\n== ENCERRAMENTO SEGURO ==")
    stopped = app.engine.shutdown()
    server.shutdown()
    server.server_close()
    print("PIDs encerrados pelo app:", stopped)
    print("processos gerenciados restantes:", app.engine.processes.snapshot())
    return 0 if doctor["checks"][0]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
