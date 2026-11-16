# Changelog — WillTechBH IA Nexus Portable

## 3.0.0-preview.1 — 2026-11-16

Primeira Pre-release pública. Tag `v3.0.0-preview.1` a ser criada sobre o commit homologado.

### Adicionado desde o develop
- Nexus Lite e Nexus Offline Complete: `nexus3.py build --profile {lite|offline|all}`.
- `nexus3.py update <pacote>`: atualização que preserva dados, modelos e configuração.
- Infraestrutura de homologação real por CI (`scripts/homologate.py`): 10 checks obrigatórios com inferência real, SSE, RAG, API e shutdown — matriz configurada em `windows-latest`, `ubuntu-latest` e `macos-latest` (ARM64).
- Launchers com checagem de Python 3.10+, validação de raiz e caminhos relativos.
- `doctor --informational` para diagnóstico no CI sem gate de prontidão.
- 12 testes de portabilidade + 6 testes de empacotamento (suíte: 64 testes).
- `dist/SHA256SUMS.txt` com os hashes dos pacotes publicados.

### Homologação
- Windows x64 e Linux x64: job nativo de CI configurado; aguardando execução e evidência da inferência real.
- macOS ARM64: E2E real local, pacote Offline Complete extraído em pasta limpa e testado; CI em `macos-latest` em validação.
- Windows ARM64, Linux ARM64 e macOS Intel permanecem experimentais (sem teste real).

### Nota
Recursos opcionais ainda não incluídos nesta preview: auto-update, shell Tauri, GPU avançada, embeddings habilitados por padrão. Ver `docs/LIMITACOES.md`.

## 3.0.0-develop — 2026-11-16

Branch isolada `develop/v3.0`. Nenhum release publicado.

### Adicionado
- Núcleo Python multiplataforma (Windows, macOS arm64/x64, Linux x64/arm64) sem dependências `pip`.
- `nexus3.py` com comandos `start`, `doctor`, `setup`, `models`, `selftest`, `build`.
- Manifesto de binários oficiais llama.cpp b12444 com SHA-256 verificado via GitHub API.
- Gerenciador de modelos com downloads resumíveis, verificação SHA-256 e promoção atômica.
- Extração segura de arquivos com preservação de symlinks relativos necessários ao macOS.
- Detecção de hardware por SO, perfis modest/intermediate/advanced e cálculo de contexto/gpu_layers.
- Nexus Intelligent Router com justificativa exibida na interface.
- 10 agentes especializados (prompts migrados da v2.0 + analista de dados).
- Ingestão local de PDF, DOCX, XLSX, CSV, TXT/MD e imagens com OCR opcional.
- RAG local BM25 persistente, citação de arquivo/página e prompt que separa extração de inferência.
- API OpenAI-compatible (`/v1/models`, `/v1/chat/completions`, `/v1/embeddings`) e `/health`.
- Busca externa opt-in na Wikipedia, desativada por padrão.
- Nexus Studio 3.0 responsivo, temas claro/escuro, histórico com busca, painel de sistema, gerenciador de modelos e diagnóstico.
- ProcessRegistry que encerra somente processos criados pela app e verificados pelo binário.
- 37 testes automatizados, smoke test de integração real e pacotes portáteis.

### Alterado
- Configuração consolidada em `config/nexus3.json` gerado em runtime; `config/nexus.json` da v2.0 não é mais usado.
- Seleção de modelo por capacidade/orçamento em vez de RAM mínima + prioridade fixa.

### Removido / substituído
- Launchers PowerShell/.bat da v2.0 substituídos por `nexus3.py` + scripts por plataforma.
- Persistência de nome de máquina/usuário substituída por ID de instalação anônimo.
- Ferramentas de shell do llama-server não são habilitadas.

### Corrigido em relação à v2.0.2
- Hashes vazios no registro de modelos e downloads sem verificação.
- `kill-nexus-processes.ps1` encerrando PIDs reaproveitados.
- Fallback para navegador não isolado.
- Divergência de URL do mmproj de visão.
- README do repositório que descrevia Ollama/AnythingLLM em vez da Release real.

## 2.0.2-ENGINE-DIAGNOSTIC — estado original

Auditoria completa em `../_audit/00-ESTADO-ORIGINAL.md`. Nenhum arquivo original foi modificado.

## 1.0.0

Tags preservadas no repositório upstream; sem alterações.
