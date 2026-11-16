# Limitações e compatibilidade — Nexus Portable 3.0 Preview 1

> **Atualizado em 16/11/2026.** Esta documentação substitui as notas pré-homologação. Windows x64, Linux x64 e macOS ARM64 **passaram** em CI com inferência real, mas a versão continua sendo uma Preview.

## Estado por plataforma

| Plataforma | Homologação | Distribuição |
|---|---|---|
| Windows x64 | ✅ Runner Windows nativo: suíte e inferência real | **Lite**; baixa motor/modelo autorizados no primeiro uso |
| Linux x64 | ✅ Runner Ubuntu nativo: suíte e inferência real | **Lite**; baixa motor/modelo autorizados no primeiro uso |
| macOS ARM64 | ✅ Runner macOS nativo + teste local em extração limpa | **Lite** ou **Offline Complete** (motor + Qwen3 0.6B Q8_0) |
| Windows ARM64 | ⚠️ Experimental; sem homologação de inferência | Sem pacote Offline Complete |
| Linux ARM64 | ⚠️ Experimental; sem homologação de inferência | Sem pacote Offline Complete |
| macOS Intel | ⚠️ Experimental; sem homologação de inferência | Sem pacote Offline Complete |

Evidência: [CI final (13/13)](https://github.com/hebwil/ia-offline/actions/runs/43973139797) e [homologação de inferência](https://github.com/hebwil/ia-offline/actions/runs/43971732157). O sucesso nos runners não comprova todas as configurações de computador.

## Dependências e distribuição

1. **Python 3.10+ é obrigatório**, instalado no computador ou disponibilizado em runtime portátil. O projeto não inclui um bootstrap universal de Python.
2. **Nexus Lite não inclui motor nem modelo.** O primeiro uso precisa de internet e autorização explícita para downloads. O pacote completo offline publicado destina-se somente ao macOS ARM64.
3. **GPU CUDA/ROCm/Vulkan não foi homologada nesta preview.** Os testes principais são de inferência CPU/runner e macOS ARM64; não prometa aceleração específica.
4. **Portabilidade não significa ausência de rastros.** O sistema operacional pode criar arquivos de cache, registros, permissões e históricos fora da pasta do aplicativo.
5. **Sistemas de arquivos:** exFAT, NTFS, APFS e ext4 possuem características de execução/permissões distintas. FAT32 não admite arquivos acima de 4 GiB. Nem todas as combinações foram testadas fisicamente.

## Funcionalidades com limitações

6. **OCR:** extração de texto em imagens/PDFs digitalizados requer Tesseract no `PATH`. Sem esse componente, o texto de imagens não deve ser presumido.
7. **RAG:** busca BM25 local disponível. Embeddings semânticos demandam modelo/servidor adicional e ficam desativados por padrão.
8. **Busca externa:** apenas integração opcional de pesquisa na Wikipédia em português, desativada por padrão. Não há navegação geral na internet, MCP ou provedores comerciais integrados nesta preview.
9. **Agentes:** são perfis de instruções especializados; não representam dez motores autônomos carregados simultaneamente. O modelo local limita a qualidade das respostas.
10. **Tool calling do modelo:** não habilitado; o aplicativo possui ferramentas determinísticas restritas, mas o modelo não recebe acesso irrestrito ao shell.
11. **Nexus Studio:** interface web servida localmente, não um app nativo Tauri/Electron. Não há auto-update assinado nesta versão.
12. **Modelos grandes e qualidade:** a inferência foi comprovada com modelo compacto; raciocínio especializado, programação e português não passaram por uma suíte pública comparativa com modelos 4B/8B/coder.
13. **Telas e acessibilidade:** interface responsiva, mas não validada exaustivamente em todos os dispositivos e tecnologias assistivas.

## Próximas etapas propostas (não prometidas)

- Pacotes Offline Complete adicionais para Windows x64 e Linux x64, com integridade e instalação em pasta limpa.
- Homologação em máquinas reais com CPU/GPU variadas.
- Melhoria da experiência inicial, sem comandos manuais onde tecnicamente viável.
- Testes de qualidade de RAG, OCR e modelos especializados.
- Atualização da documentação, capturas reais da interface e evolução do instalador.

**Não afirmar que um recurso ainda pendente está homologado.** Veja [TESTES.md](TESTES.md) e a [Release Preview 1](https://github.com/hebwil/ia-offline/releases/tag/v3.0.0-preview.1).
