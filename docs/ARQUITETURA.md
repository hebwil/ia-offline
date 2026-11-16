# Arquitetura da v3.0

## Visão geral

```
Nexus Studio (HTML/CSS/JS, estático)
        │  HTTP local 127.0.0.1
        ▼
nexus3/server.py  ── API /api/* + OpenAI-compatible /v1/*
        │
        ├─ router.py        decisão explicável (tarefa × capacidade × hardware)
        ├─ agents.py        perfis de prompt (sem processos permanentes)
        ├─ documents.py     PDF/DOCX/TXT/CSV/XLSX/imagem + OCR opcional
        ├─ rag.py           BM25 local + embeddings opcionais + citações
        ├─ tools.py         calculator/document_search com allowlist
        ├─ web.py           Wikipedia opt-in (desligado por padrão)
        ├─ models.py        registro verificado + download resumível
        └─ engine.py        llama-server: start/health/stop/swap
                    │
                    ▼
         llama-server oficial (b12444), 127.0.0.1:9931+, --api-key
```

## Fluxo de primeira execução

1. `detect_platform()` → sistema, arquitetura, chave do binário oficial.
2. `detect_hardware()` → RAM total/disponível, CPU, GPU/VRAM quando consultável, filesystem.
3. `Config.load()` mescla DEFAULTS com `config/nexus3.json` (gerado em runtime).
4. `ModelRegistry` lê `config/models.json` com SHA-256 de cada arquivo.
5. `setup --yes` baixa e verifica o motor; `models install --yes` baixa e verifica o modelo.
6. `NexusApp._auto_start()` escolhe o melhor modelo instalado e inicia o motor.
7. `wait_health()` consulta `/health` até 200 ou expira com mensagem e log.
8. Servidor HTTP local abre a interface; `doctor` confirma o estado.
9. `shutdown()` encerra somente PIDs registrados e verificados.

## Decisões principais

| Tema | Decisão | Motivo |
|---|---|---|
| Motor | llama.cpp (`llama-server`) | binários oficiais para as 4 plataformas, OpenAI-compatible, MIT |
| Ollama | não adotado como motor; provider externo opcional não implementado | exige daemon instalado fora da pasta portátil |
| Shell nativo (Tauri/Electron) | não entregue nesta versão | Rust indisponível no ambiente; Electron pesado demais |
| Backend | Python 3.10+ stdlib | zero `pip`, superfície pequena, reaproveita o proxy v2.0 |
| UI | HTML/CSS/JS sem framework | leve, responsiva, acoplável a Tauri no futuro |
| Estado | JSON atômico em `data/` com backup | portabilidade e recuperação |
| Rede | loopback + opt-in explícito | privacidade por padrão |

## Módulos

| Arquivo | Responsabilidade |
|---|---|
| `platform.py` | SO/arquitetura, descoberta de raiz, paths relativos, permissões |
| `config.py` | DEFAULTS, merge, escrita atômica, visão pública sem segredos |
| `security.py` | PathGuard, redaction, ProcessRegistry, AtomicWriter |
| `hardware.py` | perfil por SO, tiers, contexto e gpu_layers recomendados |
| `models.py` | registro, seleção por capacidade/orçamento, download verificado |
| `engine.py` | manifesto de binários, extração segura, ciclo de vida, SSE |
| `router.py` | análise de sinal, decisão e justificativa |
| `agents.py` | 10 perfis de prompt |
| `documents.py` | extração e chunks com página |
| `rag.py` | índice BM25 persistente, embeddings opcionais, prompt fundamentado |
| `tools.py` | duas ferramentas determinísticas e allowlist |
| `chat.py` | conversas persistentes e busca |
| `web.py` | busca externa explícita na Wikipedia |
| `server.py` | API local, compatibilidade OpenAI, static UI |

## Compatibilidade OpenAI

- `GET /v1/models` — modelo ativo.
- `POST /v1/chat/completions` — aceita `stream`, `temperature`, `max_tokens`; injeta perfil, documentos e histórico antes de encaminhar ao llama-server.
- `POST /v1/embeddings` — encaminhado ao motor quando um modelo de embeddings está ativo.
- `GET /health` e `GET /v1/health` — prontidão.

A chave gerada automaticamente é usada internamente. Clients externos podem definir `NEXUS3_API_KEY` e ativar `require_auth` ao construir o servidor via API Python.
