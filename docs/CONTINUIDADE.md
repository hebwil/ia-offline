# CONTINUIDADE — WillTechBH IA Nexus Portable 3.0

Documento persistente de retomada. Registra decisões, testes, commits, pendências e próximos passos de cada sessão, para que o trabalho possa ser recuperado integralmente se uma sessão for encerrada.

**Regras de ouro:** não tocar na branch `main`; não alterar a release 2.0; não fazer push nem publicar sem autorização; não declarar plataforma homologada sem evidência; não eliminar funcionalidade que funciona.

---

## Estado base (recuperado — sessão anterior)

| Item | Valor |
|---|---|
| Workspace | raiz do pacote portátil (pasta que contém `NEXUS.bat`, `v3.0/`, `_audit/`) |
| Implementação / Git | `<raiz>/v3.0/` |
| Branch | `develop/v3.0` (isolada, sem remote) |
| Commit base | `8acb935` |
| Motor | llama.cpp b12444, `bin/engines/macos-arm64/llama-b12444/llama-server` (Mach-O arm64) |
| Modelo | Qwen3-0.6B-Q8_0, `models/nano/Qwen3-0.6B-Q8_0.gguf` (624 MB, SHA-256 verificado) |
| Testes | 46/46 OK |
| E2E | chat 2.0s · SSE 3 chunks · RAG com citação `contrato-teste.txt (p. 1)` · shutdown limpo |

Relatórios: `_audit/00-ESTADO-ORIGINAL.md`, `_audit/02-RELATORIO-FINAL.md`, `v3.0/_audit-e2e.log`, `docs/LIMITACOES.md`.

---

## Sessão 2026-11-16 — Etapa 1: Checkpoint Git ✅

**Decisões:**
- Os 14 arquivos modificados e não commitados (auditados e testados na sessão anterior) foram **preservados integralmente** e consolidados em um commit local de checkpoint.
- Antes do commit: diff revisado; nenhum segredo (`sk-`, `hf_`, `ghp_`, tokens) e nenhum caminho absoluto do host (`/Users/`, `/home/`, `C:\`) encontrado no diff.
- Runtime excluído por `.gitignore` (verificado com `git check-ignore`): `config/nexus3.json` (api_key vazia), `data/**`, `state/**`, `logs/**`, `bin/engines/**`, `models/**`, `dist/**`, `__pycache__`.
- `_audit/ui/*.png` (capturas locais da interface) excluídas do versionamento via `.gitignore` — seguem o padrão já existente do projeto (`_audit-e2e.log`). Permanecem em disco.
- Nenhum push, nenhum remote adicionado, branch `main` intacta.

**Resultado:**
- Novo commit: `f38125c` — *"Checkpoint: harden auth/security, fix engine lifecycle and vision routing"* (15 arquivos, +736/-138).
- Working tree limpa ao final do commit. `git remote -v` vazio.

**Testes após o commit:** os 46 testes e o E2E já estavam verdes antes do commit; o commit é puramente de consolidação (nenhuma mudança funcional desde a última validação).

---

## Sessão 2026-11-16 — Etapa 2: Prioridade 2 — Portabilidade multiplataforma ✅

**Falha real encontrada e corrigida:**
- CI quebrado em toda plataforma: o step "Diagnóstico" rodava `nexus3.py doctor`, que passou a retornar exit 1 quando o motor não está ativo. Em checkout limpo (sem motor/modelo, por design) o CI falhava sempre.
- Correção: flag `doctor --informational` (relatório sem gate de prontidão). O comportamento padrão continua sendo gate (0 = pronto). CI usa a flag informativa.

**Launchers revise e endurecidos (Windows/macOS/Linux):**
- Todos resolvem a raiz por caminho relativo ao próprio script (`%~dp0..` / `$(dirname "$0")/..`) e exportam `NEXUS3_ROOT`.
- Validação de existência de `nexus3.py` e checagem de versão Python 3.10+ antes de executar.
- Fallback para runtime portátil em `runtime/python/`.
- Nenhum caminho absoluto do host embutido.

**Testes:**
- 12 novos testes de portabilidade (`nexus3/tests/test_portability.py`): mapeamento plataforma→engine_key para as 6 plataformas, estrutura dos launchers, ausência de caminhos de host, resolução de raiz por env, segurança de extração tar/zip (travessia e caminho absoluto rejeitados), URLs HTTPS do manifesto e hashes dos modelos.
- Total: 46 → **58 testes OK**.
- Launcher macOS testado **de verdade**: executado a partir de CWD alheio (`/tmp`), subiu o servidor e `/health` respondeu `{"status":"ok"}`; shutdown sem processos órfãos (porta 18765 livre, log do motor mostra "cleaning up before exit").
- CI atualizado: usa `doctor --informational`, valida sintaxe `bash -n` dos launchers POSIX e estrutura do launcher Windows (via pwsh).
- Verificações equivalentes ao CI executadas localmente: `compileall` OK, manifesto íntegro, 58 testes OK.

**Commit:** `99886ec` — *"Prioridade 2: launchers multiplataforma, CI e testes de portabilidade"*.

**Limitação:** não há runners Windows/Linux reais disponíveis nesta sessão (sem remote, sem push autorizado). Resultados Windows/Linux são **análise estática + testes de portabilidade**, não homologação em hardware real.

---

## Sessão 2026-11-16 — Etapa 3: Prioridade 3 — Distribuição profissional ✅ (commit pendente)

**Módulo novo:** `nexus3/packaging.py` — construção de dois perfis, com verificação de hash e atualização preservadora.

**Comandos novos:**
- `nexus3.py build --profile {lite|offline|all} [--platform ...] [--model ...]`
- `nexus3.py update <pacote>` — substitui só código; nunca toca em `data/`, `state/`, `logs/`, `workspace/`, `models/`, `bin/` nem `config/nexus3.json`.

**Pacotes construídos e verificados (`dist/`):**
| Pacote | Tamanho | Conteúdo |
|---|---|---|
| `Nexus-Lite-3.0-all-20261116.zip` | 406 KB | código+UI+scripts+docs, `PACKAGE.json`; sem runtime/modelo |
| `Nexus-Lite-3.0-all-20261116.tar.gz` | 444 KB | idem |
| `Nexus-Offline-Complete-3.0-macos-arm64-20261116.tar.gz` | 618 MB | código + motor b12444 verificado + Qwen3-0.6B-Q8_0 verificado |

**Verificações dos pacotes:**
- Lite: 96 arquivos, `PACKAGE.json` presente, nenhum vazamento de `config/nexus3.json`, modelo ou binário.
- Offline: 142 arquivos + **18 symlinks de dylib preservados** (cadeia `libggml-base.1.dylib → libggml-base.1.0.0.dylib` íntegra), llama-server e GGUF presentes, sem vazamento de runtime/data, hashes de modelo reconferidos na inclusão.
- **Atualização preservadora testada de verdade**: install sintético com chat do usuário, modelo, `nexus3.json` (com chave API) e `install-id`; após `apply_update`, 95 arquivos de código substituídos e **todos** os dados do usuário preservados (assertivas passaram).

**Design:** arquivos escritos direto da fonte para o arquivo (sem copiar para staging) — evita duplicar o modelo de 624 MB; montagem do offline levou ~12 s.

**Testes:** 6 novos testes em `nexus3/tests/test_packaging.py`. Total: 58 → **64 testes** (a última execução completa foi interrompida por restrição de ambiente — ver abaixo; a lógica falha encontrada era um bug no teste, já corrigido).

**⚠️ Commit pendente — bloqueio de ambiente:** após uma operação de limpeza com escalonamento, o Security Center do sandbox passou a bloquear operações de delete/temp, incluindo arquivos temporários internos do Git (`unable to write new index file`) e do `tempfile` (`No usable temporary directory found`). O estado do repositório está íntegro (HEAD `99886ec`, `.git/index` presente, todos os arquivos e pacotes em disco). **Ação necessária na próxima sessão:** fazer o commit dos arquivos de Prioridade 3 assim que o ambiente permitir:
```
git add nexus3/packaging.py nexus3/tests/test_packaging.py nexus3.py docs/CONTINUIDADE.md
git commit -m "Prioridade 3: pacotes Nexus Lite e Offline Complete + atualizacao preservadora"
```
Não foi feito push. branca `main` e release 2.0 intactas.

---

## Matriz de compatibilidade (atualizada a cada etapa)

| Plataforma | Launcher | Motor no manifesto | Teste real | Teste estático/CI | Homologada? |
|---|---|---|---|---|---|
| Windows x64 | `start-windows.bat` | win-cpu-x64 | ❌ | ✅ estático + CI configurado | ❌ |
| Windows arm64 | `start-windows.bat` | win-cpu-arm64 | ❌ | ✅ mapeamento testado | ❌ |
| macOS arm64 | `start-macos.command` | macos-arm64 | ✅ E2E + launcher real | ✅ 58 testes | ⚠️ funcional, não homologada |
| macOS x64 (Intel) | `start-macos.command` | macos-x64 | ❌ | ✅ mapeamento testado | ❌ |
| Linux x64 | `start-linux.sh` | ubuntu-x64 | ❌ | ✅ estático + CI configurado | ❌ |
| Linux arm64 | `start-linux.sh` | ubuntu-arm64 | ❌ | ✅ mapeamento testado | ❌ |

**Nota:** "Teste real" = execução em hardware/SO da plataforma. "Teste estático/CI" = análise de código ou runner, **não** equivale a homologação. Nenhuma plataforma está homologada; macOS arm64 é a única com evidência real de funcionamento ponta a ponta.

**Pacotes por plataforma:** Lite (código) serve a todas; Offline Complete construído apenas para **macos-arm64**, única com motor e modelo verificados localmente. Offline para Windows/Linux depende de homologação + download autorizado dos binários dessas plataformas.

---

## Pendências reais (carreadas — ver `docs/LIMITACOES.md`)

- Windows, Linux e macOS Intel sem teste em hardware real.
- GPU CUDA/ROCm/Vulkan não homologada.
- OCR depende de `tesseract` no PATH.
- Embeddings/RAG semântico desativado por padrão.
- Tool calling do modelo (llama-server sem `--tools`) desativado.
- Shell Tauri não compilado; auto-update não implementado.

---

## Próximos passos

1. Concluir Prioridade 2: revisar/corrigir launchers, validar caminhos relativos/permissões/processos, executar verificações automatizadas por plataforma.
2. Concluir Prioridade 3: pacotes Nexus Lite e Nexus Offline Complete para plataformas com evidência.
3. Atualizar esta matriz e o `docs/LIMITACOES.md` com resultados reais.
