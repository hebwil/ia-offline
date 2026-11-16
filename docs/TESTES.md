# Testes e evidências

Ambiente de execução: **macOS 27.2.0, Apple M5 Pro, ARM64, 24 GB RAM, Python 3.13.12**.
Data: 2026-11-16. Nenhum Windows, Linux ou GPU discreta estava disponível.

## 1. Suíte automatizada

```bash
cd v3.0 && python3 nexus3.py selftest
```

Resultado: **Ran 37 tests — OK**.

Cobertura:

| Área | Casos |
|---|---|
| Plataforma | detecção de SO/arquitetura, descoberta de raiz, travessia de path, redaction, backup atômico, posse de PID |
| Configuração | defaults, roundtrip, visão pública sem chave de API |
| Hardware | tiers, orçamento, contexto e gpu_layers |
| Modelos | hashes do registro, detecção de arquivo ausente/adulterado, seleção por capacidade/RAM |
| Download | retomada `Range` + hash válido (servidor HTTP local), rejeição e remoção em hash inválido |
| Documentos | TXT, CSV, DOCX, XLSX, PDF real gerado com pypdf, imagem sem OCR (não inventa texto), chunks com página |
| RAG | tokenização, BM25, citações, persistência e remoção do índice |
| Roteador | detecção de domínios, agente correto, decisão explicável, limites de temperatura |
| Ferramentas | calculadora segura (rejeita `__import__`), allowlist |
| Motor | manifesto com 6 hashes de 64 chars, comando com loopback e API key, sem `--tools` |
| API HTTP | `/health`, `/api/status`, `/v1/models`, UI estática, upload/index/search, histórico, doctor, offline default, erro 503 sem motor, 403 sem autorização de download |

## 2. Integração real (motor + modelo + RAG)

```bash
python3 nexus3.py setup --yes                       # motor b12444-macos-arm64
python3 nexus3.py models install qwen3-0.6b-q8 --yes
python3 -u scripts/e2e-smoke.py
```

Evidências (resumo do log integral em `v3.0/_audit-e2e.log`):

- Motor: `bin/engines/macos-arm64/llama-b12444/llama-server`, arquivo com SHA-256 **verificado**, 18 symlinks de dylib preservados.
- Inicialização: `qwen3-0.6b-q8`, porta 9931, contexto 8192, `/health` 200, `startup_errors: []`.
- Chat não-stream: resposta real em português, `source=local`, roteador `geral`, 1,9 s.
- Chat stream SSE: 2 chunks recebidos, resposta final `pronto`, 1,4 s.
- Documento: upload de TXT → 1 chunk → pergunta fundamentada → resposta `"O prazo ... é de 45 dias, citado na Clausula Unica do contrato-teste.txt"`, `source=local+documentos`, citação `contrato-teste.txt (p. 1)`.
- Diagnóstico: 6 checks OK; OCR local e modo online corretamente reportados como indisponíveis/desativados.
- Encerramento: PID 44203 encerrado pelo app; nenhum processo gerenciado restante.

Bug real encontrado e corrigido durante esta validação: o extrator original ignorava symlinks, causando `dyld: Library not loaded: @rpath/libllama-common.1.dylib`. O extrator agora preserva symlinks relativos seguros.

## 3. Pacotes

```bash
python3 nexus3.py build
```

- `dist/WillTechBH-IA-Nexus-3.0-win-portable-20261116.zip` — 373 KB.
- `dist/WillTechBH-IA-Nexus-3.0-unix-portable-20261116.tar.gz` — 335 KB.

Conferido: nenhum `config/nexus3.json` (runtime) ou arquivo `.pyc` embarcado. Pacotes não incluem modelos/engines — estes são obtidos com autorização e verificação no primeiro uso.

## 4. O que não foi testado aqui

- Windows 10/11 (nenhum host disponível): launchers `.bat` escritos e revisados, mas **não executados**.
- Linux x86_64/ARM64: binários no manifesto, mas não executados.
- CUDA / ROCm / Vulkan: sem GPU no ambiente; fallback CPU/Metal homologado no macOS ARM64.
- Modo online: implementado e desativado por padrão; não exercitado contra a Wikipedia nesta missão.
- OCR local: `tesseract` ausente; o sistema reporta a limitação em vez de simular.
- Modelos de 4B/8B/coder/visão/embeddings: registro e hashes verificados via API, downloads **não** executados (tamanhos maiores).
- Troca de letra de drive e ponto de montagem: lógica implementada e testada por unidade, não em sistema real.

Esses itens permanecem como pendências explícitas — ver `LIMITACOES.md`.
