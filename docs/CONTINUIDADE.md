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

## Sessão 2026-11-16 — Etapa 3: Prioridade 3 — Distribuição profissional ✅ (commit concluído)

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

**Bloqueio de ambiente resolvido:** após uma operação de limpeza com escalonamento, o Security Center do sandbox bloqueou temporariamente operações de delete/temp, incluindo arquivos temporários internos do Git (`unable to write new index file`) e do `tempfile` (`No usable temporary directory found`). O estado do repositório permaneceu íntegro. Assim que o ambiente voltou a permitir escrita, o commit foi concluído: `2cfd51a` — *"Prioridade 3: pacotes Nexus Lite e Offline Complete + atualizacao preservadora"*. Nenhum push foi feito nesta etapa; `main` e a release 2.0 permanecem intactas.

---

## Sessão 2026-11-16 — Etapa 4: fechamento, homologação e publicação (em execução)

**Correções objetivas aplicadas antes do push:**
- Matriz de homologação do CI: runner `macos-14` (descontinuado e x64) substituído por `macos-latest` (Apple Silicon ARM64) — o job `homologacao` agora aponta para a arquitetura que pretende homologar.
- `README.md` e `CHANGELOG.md` deixaram de afirmar homologação Windows/Linux por CI antes da execução do runner; os status passaram a distinguir evidência local de evidência pendente de CI.
- Nenhuma funcionalidade foi removida ou reconstruída.

**Evidências locais já produzidas:**
- Suíte completa após as correções: **64/64 testes OK**.
- Homologação real local em macOS ARM64 (`scripts/homologate.py`): **10/10 checks PASS** — motor verificado, processo ativo, `/health`, chat real, justificativa do roteador, SSE, citação RAG, checks críticos do doctor e shutdown limpo. Evidência em `logs/homologation-evidence.json`.
- Pacote Offline Complete extraído em pasta limpa: hashes conferidos, **18 symlinks preservados** e inferência real executada a partir da extração.
- `dist/SHA256SUMS.txt` gerado e verificado para os três pacotes publicáveis.
- `gh` autenticado como `hebwil` com permissão `ADMIN` no repositório público `hebwil/ia-offline`.

**Push e CI:** após a expansão do escopo `workflow`, `develop/v3.0` foi publicada com os commits existentes. A primeira CI (`43971065550`) falhou somente nos jobs Python 3.10: o `pypdf` vendido importava `typing_extensions.Self`, ausente no runtime stdlib. Correção objetiva em `492835a`: fallback para `typing.TypeVar` nos dois pontos de importação; teste afetado validado e import simulado em Python 3.10. A segunda CI (`43971732157`, commit `492835a`) terminou **success**: 13 jobs verdes, incluindo `integrity`, 9 jobs de teste (Windows/macOS/Linux × Python 3.10/3.12/3.13) e os 3 jobs de homologação com inferência real em `windows-latest`, `ubuntu-latest` e `macos-latest` ARM64. Evidência: `https://github.com/hebwil/ia-offline/actions/runs/43971732157`.

**Pacotes finais:** reconstruídos a partir do commit `492835a`; `SHA256SUMS.txt` regenerado e verificado. Os três arquivos publicáveis contêm a correção Python 3.10.

**Estado atual:** branch `develop/v3.0` publicada; tag e release 3.0 ainda não criadas. `main`, `v1.0.0`, `v2.0.0` e a release 2.0 permanecem intactas.

**Próxima ação:** registrar as evidências finais em README/CHANGELOG, fazer commit, repetir a CI no commit final e somente então criar tag e Pre-release.

---

## Matriz de compatibilidade (atualizada a cada etapa)

| Plataforma | Launcher | Motor no manifesto | Evidência real | CI nativa (inferência real) | Homologada? |
|---|---|---|---|---|---|
| Windows x64 | `start-windows.bat` | win-cpu-x64 | inferência real em CI | ✅ `windows-latest`, job `homologacao` | ✅ homologada |
| Windows arm64 | `start-windows.bat` | win-cpu-arm64 | ❌ | ❌ | ❌ (experimental) |
| macOS arm64 | `start-macos.command` | macos-arm64 | E2E local, pacote extraído, 10/10 checks + inferência real em CI | ✅ `macos-latest`, job `homologacao` | ✅ homologada |
| macOS x64 (Intel) | `start-macos.command` | macos-x64 | ❌ | ❌ | ❌ (experimental) |
| Linux x64 | `start-linux.sh` | ubuntu-x64 | inferência real em CI | ✅ `ubuntu-latest`, job `homologacao` | ✅ homologada |
| Linux arm64 | `start-linux.sh` | ubuntu-arm64 | ❌ | ❌ | ❌ (experimental) |

**Nota:** "Evidência real" = inferência executada no SO/hardware da plataforma. As três plataformas obrigatórias foram homologadas por job de CI com inferência real no run `43971732157`.

**Pacotes por plataforma:** Lite (código) serve a todas; Offline Complete construído apenas para **macos-arm64**, única com motor e modelo verificados localmente. Offline para Windows/Linux depende de homologação + download autorizado dos binários dessas plataformas.

---

## Pendências reais (carreadas — ver `docs/LIMITACOES.md`)

- Windows ARM64, Linux ARM64 e macOS Intel: experimentais, sem teste real.
- GPU CUDA/ROCm/Vulkan não homologada.
- OCR depende de `tesseract` no PATH.
- Embeddings/RAG semântico desativado por padrão.
- Tool calling do modelo (llama-server sem `--tools`) desativado.
- Shell Tauri não compilado; auto-update não implementado.

---

## Próximos passos

1. Fazer commit das evidências finais em README/CHANGELOG/CONTINUIDADE e repetir a CI no commit final.
2. Criar tag `v3.0.0-preview.1` no commit homologado.
3. Publicar a Pre-release `WillTechBH IA Nexus Portable 3.0 — Preview 1` com os três pacotes e `SHA256SUMS.txt`.
4. Verificar URLs públicas da release e dos anexos, e confirmar que `main`, `v1.0.0`, `v2.0.0` e a release 2.0 permanecem intactos.
