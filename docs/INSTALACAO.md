# Instalação — WillTechBH IA Nexus Portable 3.0

> **Preview 1:** antes de instalar, [consulte os downloads oficiais](https://github.com/hebwil/ia-offline/releases/tag/v3.0.0-preview.1). O núcleo é multiplataforma, mas os pacotes e pré-requisitos diferem. Para uma primeira experiência, use o modelo compacto Qwen3 0.6B Q8_0.

## O que baixar?

| Sistema | Pacote recomendado | Inclui motor e modelo? |
|---|---|---|
| Windows 10/11 x64 | `Nexus-Lite-3.0-all-20261116.zip` | ❌ Não; serão baixados com autorização |
| Linux x64 | `Nexus-Lite-3.0-all-20261116.tar.gz` | ❌ Não; serão baixados com autorização |
| macOS Apple Silicon | `Nexus-Offline-Complete-3.0-macos-arm64-20261116.tar.gz` | ✅ Sim, inclui `llama-server` e Qwen3 0.6B Q8_0 |
| macOS Apple Silicon (modo Lite) | `Nexus-Lite-3.0-all-20261116.tar.gz` | ❌ Não |

**Requisito comum: Python 3.10 ou superior.** O núcleo usa a biblioteca padrão do Python, mas isso não elimina a necessidade de ter o Python instalado ou disponível em `runtime/`. Sem Python compatível, o launcher exibirá uma mensagem. Confirme também RAM e armazenamento suficientes para o modelo escolhido.

**Integridade:** compare o SHA-256 do pacote baixado com [SHA256SUMS.txt](https://github.com/hebwil/ia-offline/releases/download/v3.0.0-preview.1/SHA256SUMS.txt).

## Windows x64 — Nexus Lite

1. Baixe o ZIP, extraia em uma pasta do SSD ou pendrive (por exemplo, `D:\Nexus3`). Entre nessa pasta usando PowerShell ou Terminal. Ela deve conter `nexus3.py` e o diretório `scripts`.
2. Confirme o Python: `py -3 --version` (ou `python --version`). É necessário Python 3.10+.
3. Execute:

```powershell
py -3 nexus3.py setup --yes
py -3 nexus3.py models install qwen3-0.6b-q8 --yes
py -3 nexus3.py doctor
py -3 nexus3.py start
```

O comando `setup` obtém o motor verificado para Windows x64 e `models install` obtém o modelo. A interface abre no navegador local. Para iniciar novamente depois de instalar, execute `scripts\start-windows.bat` ou `py -3 nexus3.py start`.

## Linux x64 — Nexus Lite

1. Extraia o TAR.GZ em uma pasta com permissão de escrita e execução.
2. Confirme `python3 --version` (3.10+).
3. Na pasta com `nexus3.py`, execute:

```bash
python3 nexus3.py setup --yes
python3 nexus3.py models install qwen3-0.6b-q8 --yes
python3 nexus3.py doctor
python3 nexus3.py start
```

O atalho `scripts/start-linux.sh` pode ser usado depois da preparação. Caso necessário: `chmod +x scripts/start-linux.sh`.

## macOS Apple Silicon — Offline Complete

1. Baixe `Nexus-Offline-Complete-3.0-macos-arm64-20261116.tar.gz`.
2. Extraia com ferramenta que preserve **symlinks relativos**; o `tar` nativo é apropriado. Não utilize ferramentas que substituam symlinks por cópias incompletas.
3. Na pasta extraída que contém `nexus3.py`, verifique `python3 --version` (3.10+).
4. Inicie:

```bash
python3 nexus3.py doctor
python3 nexus3.py start
```

O pacote já inclui motor e modelo. **Não é necessário rodar `setup` nem instalar modelo novamente**, desde que os arquivos estejam íntegros e seu ambiente suporte a execução.

Se optar pelo Lite no Mac, execute o mesmo procedimento de download do motor e do modelo mostrado em Linux antes de iniciar.

## Como usar

- Mantenha o processo `nexus3.py start` em execução enquanto estiver usando a interface.
- O endereço local tem a forma `http://127.0.0.1:PORTA/`; a porta real aparece no Terminal.
- Envie perguntas, adicione documentos textuais ou escolha um modelo instalado na interface.
- Para encerrar, interrompa o processo pelo Terminal. O aplicativo deve encerrar apenas processos que gerencia.
- Não é necessário criar conta em serviço de IA para o processamento local.

## Pendrive, SSD e atualização

- **SSD externo é preferível** para modelos grandes e leitura rápida; pendrives lentos podem prejudicar downloads e inicialização.
- **exFAT:** facilita troca entre sistemas, mas permissões de execução e binários ainda variam; executáveis Windows não funcionam nativamente em macOS/Linux.
- **FAT32:** não suporta arquivos individuais maiores que 4 GiB.
- **Mudança de letra da unidade:** os launchers usam a localização relativa à pasta do aplicativo.
- **Atualização controlada:** utilize `python3 nexus3.py update CAMINHO_DO_PACOTE`, quando apropriado, após fazer backup. O fluxo foi desenvolvido para preservar `data/`, `models/`, `state/` e a configuração do usuário. Leia a documentação e não substitua essas pastas manualmente.

## Erros comuns

| Sintoma | Verificação |
|---|---|
| Python não encontrado | Instale Python 3.10+ ou configure runtime portátil compatível. |
| Motor não encontrado | No Lite, rode `setup --yes` com internet. |
| Modelo não encontrado | Rode `models list` e instale o modelo desejado com `models install ID --yes`. |
| A interface não abre | Confira a porta informada no Terminal e o resultado de `doctor`. |
| Arquivos de biblioteca não encontrados no macOS | Extraia novamente preservando symlinks. |
| OCR não funciona | Requer Tesseract instalado separadamente. |
| Desempenho insuficiente | Teste modelo menor e reduza contexto; GPU não está homologada nesta preview. |

Leia [TESTES.md](TESTES.md) para comprovações e [LIMITACOES.md](LIMITACOES.md) para os pontos que ainda não foram validados. Não use instruções antigas de Ollama/AnythingLLM para a v3.0.
