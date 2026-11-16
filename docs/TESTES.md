# Testes e evidências — Nexus Portable 3.0 Preview 1

> **Estado em 16/11/2026.** Este documento consolida a homologação final. Os primeiros testes foram realizados no macOS ARM64; os testes multiplataforma posteriores ocorreram em runners nativos do GitHub Actions. A versão pública é [v3.0.0-preview.1](https://github.com/hebwil/ia-offline/releases/tag/v3.0.0-preview.1), commit `2501b81a9e3db3dea9c0dfa15d25abc1684ec895`.

## Resultado consolidado

| Plataforma | Runner | Suíte automatizada | Inferência local real | Observação |
|---|---|---|---|---|
| Windows x64 | `windows-latest` | 64/64 em Python 3.10, 3.12 e 3.13 | ✅ Job `homologacao` aprovado | CI nativo; não equivale a todos os hardwares Windows |
| Linux x64 | `ubuntu-latest` | 64/64 em Python 3.10, 3.12 e 3.13 | ✅ Job `homologacao` aprovado | CI nativo; GPU não homologada |
| macOS ARM64 | `macos-latest` | 64/64 em Python 3.10, 3.12 e 3.13 | ✅ Job `homologacao` aprovado | Também houve execução local e teste do pacote Offline Complete |

**CI final:** [Run 43973139797 — 13/13 jobs concluídos com sucesso](https://github.com/hebwil/ia-offline/actions/runs/43973139797).  
**Homologação com inferência real:** [Run 43971732157 — 13/13 jobs concluídos com sucesso](https://github.com/hebwil/ia-offline/actions/runs/43971732157).

O pipeline contém 9 jobs de teste (três versões de Python por sistema), 3 de homologação e 1 de integridade.

## Como reproduzir a suíte

Na raiz da versão 3.0, com Python 3.10+:

```bash
python3 nexus3.py selftest
```

No Windows, use `py -3 nexus3.py selftest` se `python3` não estiver disponível.

Para os testes de inferência, consulte `scripts/homologate.py`, `scripts/e2e-smoke.py` e `.github/workflows/ci.yml`. Os testes funcionais exigem motor e modelo compatíveis instalados; `doctor --informational` é somente diagnóstico e **não comprova inferência**.

A matriz cobre detecção de plataforma, caminhos portáteis, configuração, segurança, downloads verificados, modelos, roteador, agentes, documentos, RAG, API, inicializadores e empacotamento.

## Evidência adicional — Offline Complete macOS ARM64

O pacote `Nexus-Offline-Complete-3.0-macos-arm64-20261116.tar.gz` foi extraído em uma pasta limpa. Foram verificados o binário, o modelo Qwen3 0.6B Q8_0, **18 symlinks de bibliotecas dinâmicas** e a execução de inferência **sem novos downloads**. O teste relatado cumpriu 10/10 verificações funcionais.

O pacote contém motor e modelo, mas exige Python 3.10+ no host ou runtime portátil compatível. Portanto, **offline completo não significa totalmente independente de Python**.

## Integridade dos anexos publicados

Os arquivos estão na [Release](https://github.com/hebwil/ia-offline/releases/tag/v3.0.0-preview.1), acompanhados de [SHA256SUMS.txt](https://github.com/hebwil/ia-offline/releases/download/v3.0.0-preview.1/SHA256SUMS.txt). Os hashes foram divulgados no lançamento e devem ser conferidos após o download.

## Limites da homologação

- Windows ARM64, Linux ARM64 e macOS Intel: sem prova final de execução real.
- CUDA, ROCm e Vulkan: não homologados em GPUs específicas.
- OCR local: exige instalação separada do Tesseract.
- Embeddings: caminho opcional, não habilitado por padrão.
- Avaliação de qualidade em português, programação e documentos complexos: não há benchmark comparativo sistemático.
- Portabilidade entre múltiplas unidades/dispositivos físicos e em todos os sistemas de arquivos: não exaustivamente homologada.
- Testes CI nativos não substituem ensaios em hardware real de usuários.

Para requisitos e restrições, consulte [LIMITACOES.md](LIMITACOES.md). Para instalar, veja [INSTALACAO.md](INSTALACAO.md).
