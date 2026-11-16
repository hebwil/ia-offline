# WillTechBH IA Nexus Portable 3.0

**IA local, portátil e realmente multiplataforma — Windows · macOS · Linux.**

> IA para quem precisa de resultado, não de assinatura.

Status: **`v3.0.0-preview.1` — Pre-release.** Homologação final em validação na CI desta branch; veja a matriz abaixo e `docs/CONTINUIDADE.md`.
As tags `v1.0.0` e `v2.0.0` e todos os arquivos da versão 2.0 permanecem intactos.

**Matriz de compatibilidade**

| Plataforma | Status | Evidência |
|---|---|---|
| Windows x64 | aguardando evidência da CI | runner nativo `windows-latest`, job `homologacao` com inferência real |
| Linux x64 | aguardando evidência da CI | runner nativo `ubuntu-latest`, job `homologacao` com inferência real |
| macOS ARM64 | homologada localmente; CI em validação | E2E real local + pacote Offline Complete extraído e testado + job `homologacao` em `macos-latest` |
| Windows ARM64 · Linux ARM64 · macOS Intel | experimentais | binário no manifesto, sem teste real — não homologadas |

> "Homologada" exige inferência real comprovada, não apenas presença do binário no manifesto.

---

## O que é

Um sistema de IA que roda a partir da própria pasta, em SSD externo ou pendrive. O computador hospedeiro empresta CPU/RAM/GPU; o projeto guarda modelos, histórico, documentos, configuração e logs. Trocar a letra do drive ou o ponto de montagem não exige reconfiguração.

- **Offline por padrão.** Nenhuma requisição externa sem escolha explícita do usuário.
- **Motor llama.cpp oficial**, com SHA-256 verificado antes de cada instalação.
- **Nexus Studio 3.0**: chat com streaming, temas claro/escuro, histórico, documentos e diagnóstico.
- **Roteador inteligente**: escolhe modelo, agente, contexto, temperatura e explica o motivo.
- **RAG local**: PDF, DOCX, TXT/MD/CSV/XLSX e imagens, com citação de arquivo e página.
- **API OpenAI-compatible** (`/v1/models`, `/v1/chat/completions`, `/v1/embeddings`).

---

## Início rápido

Requisito único: **Python 3.10+**. Não é necessário `pip` para o núcleo.

```bash
# 1. Instalar motor verificado para a sua plataforma (autorização explícita)
python3 nexus3.py setup --yes

# 2. Instalar um modelo compacto (autorização explícita; hash verificado)
python3 nexus3.py models install qwen3-0.6b-q8 --yes

# 3. Diagnóstico
python3 nexus3.py doctor

# 4. Iniciar
python3 nexus3.py start
```

A interface abre em `http://127.0.0.1:<porta>/`. Atalhos por plataforma em `scripts/`.

No Windows: `scripts\start-windows.bat`. No macOS: `scripts/start-macos.command`. No Linux: `scripts/start-linux.sh`.

> O primeiro uso baixa componentes. Modelos grandes **nunca** são baixados sem confirmação. O tamanho e o SHA-256 aparecem antes da confirmação.

---

## Comandos

| Comando | Função |
|---|---|
| `nexus3.py start [--port N] [--no-browser]` | inicia motor + interface |
| `nexus3.py doctor` | relatório de hardware, motor, modelos, OCR e modo online |
| `nexus3.py setup --yes` | instala o llama-server oficial verificado |
| `nexus3.py models list` | lista modelos com estado de instalação e hash |
| `nexus3.py models recommend` | recomenda modelo para o hardware atual |
| `nexus3.py models install <id> --yes` | baixa e verifica um modelo |
| `nexus3.py models select <id>` | troca o modelo ativo com segurança |
| `nexus3.py doctor --informational` | relatório sem usar o exit code como gate (usado no CI) |
| `nexus3.py selftest` | executa os 64 testes automatizados |
| `nexus3.py build --profile {lite\|offline\|all}` | gera pacotes Nexus Lite / Offline Complete em `dist/` |
| `nexus3.py update <pacote>` | atualiza o código preservando dados, modelos e configuração |
| `python scripts/homologate.py` | prova de inferência real (10 checks) usada na homologação |

## Pacotes

| Pacote | Conteúdo | Uso |
|---|---|---|
| **Nexus Lite** (`.zip` / `.tar.gz`, ~400 KB) | código, UI, scripts, docs | obtém motor e modelo no primeiro uso, mediante autorização |
| **Nexus Offline Complete** (`.tar.gz`, ~618 MB) | código + llama-server b12444 + Qwen3 0.6B Q8_0, todos verificados | funciona sem internet após a preparação |

O pacote Offline Complete desta preview destina-se apenas a **macOS ARM64** (plataforma com motor e modelo verificados e inferência real comprovada localmente). Conferência de integridade em `dist/SHA256SUMS.txt`.

---

## Perfis de hardware

| Perfil | RAM | Modelo padrão recomendado | Contexto |
|---|---|---|---|
| Modesto | 4–8 GB | Qwen3 0.6B Q8_0 / Qwen3 4B Q4_K_M | 1024–4096 |
| Intermediário | 8–16 GB | Qwen3 4B ou 8B Q4_K_M | 4096–8192 |
| Avançado | 16 GB+ ou VRAM 12 GB+ | Qwen3 8B, coder ou visão | 8192+ |

O context é limitado por RAM disponível e pelo teto do modelo. Se não houver GPU, `gpu_layers=0` e o sistema funciona em CPU.

---

## Segurança e privacidade

- Servidor escuta **apenas em 127.0.0.1**, com chave de API gerada por instalação.
- Nenhum endpoint executa comandos do host. Ferramentas de shell **não** são expostas ao modelo.
- Downloads usam `.part`, retomada por `Range`, verificação SHA-256 e promoção atômica.
- Extração de arquivos rejeita travessia de diretório, links absolutos e hard links; preserva apenas symlinks relativos necessários ao llama.cpp.
- Logs redatam chaves, tokens e diretórios de usuário.
- O ID de instalação é um UUID local — sem nome de máquina ou usuário.
- Somente PIDs criados pela aplicação são encerrados, e somente após conferência do binário.

**Rastros:** o sistema operacional pode criar caches, registros e arquivos temporários fora da pasta. A v3.0 minimiza e documenta esse efeito, mas não promete ausência absoluta.

---

## Documentação

- `docs/ARQUITETURA.md` — decisões, fluxos e módulos.
- `docs/INSTALACAO.md` — primeiro uso por plataforma e sistemas de arquivos.
- `docs/TESTES.md` — evidências reais de execução.
- `docs/LIMITACOES.md` — pendências e itens não homologados.
- `docs/CONTINUIDADE.md` — registro de decisões, commits, testes e retomada.
- `docs/THIRD-PARTY.md` — licenças e atribuições.
- `../_audit/00-ESTADO-ORIGINAL.md` — auditoria da v2.0.2.
- `../_audit/01-ARQUITETURA-V3.md` — pesquisa e justificativas.

---

## Licença

© 2026 WillTechBH. Componentes de terceiros mantêm suas licenças originais — veja `docs/THIRD-PARTY.md` e `MANIFEST.json`.
