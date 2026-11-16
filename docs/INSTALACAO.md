# Instalação e primeiro uso

## Requisitos

- Python **3.10+** (núcleo é stdlib; não exige `pip`).
- 4 GB de RAM para o modelo nano; 8–16 GB para uso confortável.
- Espaço: ~17–25 MB de motor + 0,64 GB (nano) a 5 GB (modelo intermediário).
- Internet **apenas** na instalação do motor e dos modelos escolhidos.

## Windows 10/11 x64 (prioritário)

1. Copie a pasta `WillTechBH-IA-Nexus-3.0` para um caminho simples (ex.: `D:\Nexus3`).
2. `python nexus3.py setup --yes` — baixa `llama-b12444-bin-win-cpu-x64.zip`, verifica SHA-256 e extrai.
3. `python nexus3.py models install qwen3-4b-q4 --yes` (ou `qwen3-0.6b-q8 --yes` em PCs modestos).
4. `python nexus3.py doctor`.
5. `scripts\start-windows.bat` (ou `python nexus3.py start`).

Binários CUDA 12.4/13.5 e ARM64 existem no mesmo release, mas o pacote padrão usa CPU com fallback seguro. Para usar GPU, substitua o arquivo do manifesto por um asset CUDA verificado e atualize o SHA-256 em `nexus3/engine.py`.

## macOS Apple Silicon / Intel

1. Copie a pasta para SSD externo ou pasta local.
2. `python3 nexus3.py setup --yes` — escolhe automaticamente `macos-arm64` ou `macos-x64`.
3. Instale um modelo e execute `doctor`.
4. `chmod +x scripts/start-macos.command && ./scripts/start-macos.command`.

O pacote macOS contém symlinks de dylib versionados; o extrator da v3.0 os preserva com validação de segurança. Não reextraia com ferramentas que descartem symlinks.

## Linux x86_64 / ARM64

1. `python3 nexus3.py setup --yes` — baixa `ubuntu-x64` ou `ubuntu-arm64`.
2. Modelo + `doctor` + `scripts/start-linux.sh`.
3. Em sistemas sem `python3` no PATH, coloque um runtime em `runtime/python/bin/python3`.

## Sistemas de arquivos

| Sistema | Observação |
|---|---|
| NTFS | recomendado no Windows; suporta permissões e nomes longos. |
| exFAT | portátil, mas sem permissões de execução; o launcher pode precisar de `python` no host. Tamanhos de arquivo >4 GB são suportados. |
| APFS | recomendado no macOS. |
| ext4 | recomendado no Linux. |
| FAT32 | **não suporta arquivos acima de 4 GB**; modelos GGUF maiores falharão. |

A detecção automática de filesystem é melhor esforço; quando o SO bloqueia a consulta, o campo aparece como `unknown` — isso não impede a execução.

## Mudança de letra/point de montagem

A raiz é descoberta em cada execução a partir da localização de `nexus3.py`. Se precisar forçar:

```bash
export NEXUS3_ROOT=/Volumes/SSD/Nexus3     # macOS/Linux
set NEXUS3_ROOT=E:\Nexus3                  # Windows
```

Nenhum caminho absoluto é gravado na configuração.

## Atualização controlada

1. Substitua somente `nexus3.py`, `nexus3/` e `config/models.json`.
2. Não apague `data/`, `models/`, `state/` nem `config/nexus3.json`.
3. Execute `python3 nexus3.py doctor` e `python3 nexus3.py selftest`.
4. Se o build do motor mudar, atualize `ENGINE_BUILD`/`ENGINE_MANIFEST` com os digests oficiais.
