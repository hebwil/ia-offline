# Licenças e atribuições de terceiros

| Componente | Versão | Origem | Licença | Uso na v3.0 |
|---|---|---|---|---|
| pypdf | 5.9.0 | `proxy/vendor/pypdf` da Release v2.0.2 (HuggingFace/pypdf) | MIT | Extração de texto de PDF; copiado integralmente para `nexus3/vendor/pypdf` |
| llama.cpp (llama-server) | build b12444 | https://github.com/ggml-org/llama.cpp | MIT | Motor de inferência; binário baixado do release oficial, `LICENSE` incluído no pacote |
| Qwen3 0.6B / 4B / 8B GGUF | — | https://huggingface.co/Qwen | Apache-2.0 | Modelos de texto no registro |
| Qwen2.5-Coder 7B Instruct GGUF | — | https://huggingface.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF | Apache-2.0 | Perfil de código |
| MiniCPM-V 4.6 GGUF + mmproj | — | https://huggingface.co/ggml-org/MiniCPM-V-4.6-GGUF | Apache-2.0 | Perfil de visão |
| EmbeddingGemma 300M GGUF | — | https://huggingface.co/ggml-org/embeddinggemma-300m-gguf | Gemma (consultar ficha) | RAG semântico opcional |
| Wikipedia (pt) | API REST | https://pt.wikipedia.org | CC BY-SA | Busca externa opt-in; URL da fonte incluída no contexto |

## Notas

- Nenhum binário de terceiros foi incorporado ao repositório: engines e modelos são baixados pelo usuário, com URL e SHA-256 declarados em `MANIFEST.json` e `config/models.json`.
- O texto da licença MIT do pypdf está em `nexus3/vendor/pypdf/__init__.py` e no repositório upstream; a atribuição aqui preserva os créditos.
- O código dos agentes especialistas deriva de `prompts/specialists.json` da Release v2.0.2, de autoria WillTechBH.
- Conteúdo da Wikipedia é apresentado com a URL de origem; o usuário deve observar CC BY-SA ao redistribuir respostas que o incorporam.
