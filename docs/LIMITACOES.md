# Pendências e limitações explícitas

## Homologação

1. **Windows 10/11**: launchers e manifesto prontos, mas não executados nesta missão (ambiente macOS). Antes de distribuir: rodar `setup`, `selftest` e `e2e-smoke.py` em Windows x64.
2. **Linux x86_64/ARM64**: mesmo procedimento pendente.
3. **macOS Intel (x64)**: binário oficial no manifesto, não executado.
4. **GPU**: CUDA/ROCm/Vulkan não homologados. O fallback CPU está funcional; no macOS ARM64 o modelo roda via backend padrão do binário oficial.
5. **exFAT/FAT32/APFS/ext4**: documentado, mas somente o filesystem do host macOS foi usado (reportado como `unknown` quando a consulta ao SO é bloqueada).

## Funcionalidades incompletas ou parciais

6. **OCR local**: depende de `tesseract` no PATH. Sem ele, imagens são sinalizadas como não interpretáveis; visão por modelo GGUF requer instalação explícita do MiniCPM-V 4.6 e do mmproj.
7. **Embeddings/RAG semântico**: implementado o caminho híbrido, mas desativado por padrão (`rag.use_embeddings=false`) porque exige um segundo modelo e servidor. O BM25 local funciona sem dependências.
8. **Busca externa**: apenas Wikipedia em português, opt-in. Não há provedores personalizados, APIs OpenAI pagas nem MCP nesta versão.
9. **Tool calling do modelo**: `tools.py` oferece duas ferramentas determinísticas ao aplicativo, mas o llama-server é iniciado **sem** `--tools` (nenhum acesso a arquivos/shell pelo modelo). Chamadas de ferramenta pelo modelo ficam pendentes de política de permissão revisada.
10. **Shell Tauri nativo**: não compilado (Rust indisponível no ambiente). A API HTTP local permite acoplá-lo depois sem reescrever o backend.
11. **Atualização automática**: há fluxo controlado manual (substituir código, preservar dados). Não há auto-update assinado.

## Operacionais

12. **Primeira execução sem Python**: o pacote assume Python 3.10+ no host ou um runtime portátil em `runtime/`. Um bootstrap de Python embeddable por plataforma não foi implementado nesta versão.
13. **Logs de Hamiltonian/telemetria**: não há telemetria. Logs locais podem conter caminhos relativos e mensagens redatadas; ainda assim, usuários devem revisar antes de compartilhar.
14. **Modelos grandes**: não baixados nesta missão (exceto Qwen3 0.6B Q8_0, 639 MB, explicitamente verificado). Qualidade em pt-BR de 4B/8B/coder/visão não foi medida com benchmarks próprios — a seleção usa metadados oficiais e licenças verificadas.
15. **Benchmarks de desempenho**: apenas tempos observados no smoke test com 0.6B; não há suíte de latência/qualidade comparativa entre modelos.
16. **Interface em telas muito pequenas**: responsiva por CSS, mas não testada em dispositivos móveis reais.

## Riscos conhecidos do legado que foram corrigidos

A v2.0.2 tinha: hashes vazios no registro, downloads sem verificação, PID reuse em kill scripts, fallback para navegador não isolado, PII em claro em `data/hosts/`, AVX nunca detectado, `.bat` inexistentes citados em mensagens e README do repositório desatualizado em relação à Release. Todos esses pontos foram substituídos ou removidos na v3.0; os detalhes estão em `../_audit/00-ESTADO-ORIGINAL.md`.

## Critério de conclusão

A v3.0 **não deve ser apresentada como concluída** até que os itens 1–5 sejam homologados em seus respectivos sistemas e os itens 7–10 sejam implementados ou formalmente descartados pelo proprietário.
