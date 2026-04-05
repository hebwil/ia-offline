# 🧠 WillTechBH IA Offline

### IA local completa no Pen Drive — Zero instalação. Zero custo. Zero nuvem.

[![Licença](https://img.shields.io/badge/Licença-Proprietária-red.svg)](LICENSE)
[![Plataforma](https://img.shields.io/badge/Plataforma-Windows-blue.svg)]()
[![Ollama](https://img.shields.io/badge/Motor-Ollama-black.svg)](https://ollama.com)
[![AnythingLLM](https://img.shields.io/badge/Interface-AnythingLLM-purple.svg)](https://anythingllm.com)

</div>

---

## 🚀 O que é isso?

**WillTechBH IA Offline** é um sistema de Inteligência Artificial completo que roda 100%
no seu Pen Drive ou SSD externo — sem instalar absolutamente nada no computador que for usar.

Você pluga, executa um arquivo `.bat` e em minutos tem uma IA de nível profissional
funcionando, seja em casa, no trabalho, no escritório do cliente ou em qualquer PC Windows.

---

## ⚡ Funcionalidades

- ✅ **Zero instalação** no PC hospedeiro — nenhum arquivo é gravado no Windows
- ✅ **Zero rastro** — ao ejetar o drive, o PC fica exatamente como estava
- ✅ **Zero custo** — nenhuma assinatura, nenhuma API key, nenhuma conta obrigatória
- ✅ **Zero nuvem** — processamento 100% local, seus dados nunca saem do drive
- ✅ **Auto-detecção de hardware** — detecta RAM, GPU (NVIDIA/AMD/Intel) e escolhe o modelo ideal
- ✅ **5 tiers automáticos** — do Nano (4GB RAM) ao Ultra (32GB+ RAM)
- ✅ **Aceleração automática** — CUDA (NVIDIA), ROCm (AMD RX7000), Vulkan (outras GPUs)
- ✅ **Visão computacional** — analisa imagens (tiers 16GB+)
- ✅ **Web Bonus automático** — se tiver internet, a IA busca dados em tempo real sem você fazer nada
- ✅ **Especialista em direito brasileiro** — CLT, Código Civil, PJe, STJ, STF, TJMG
- ✅ **Especialista em programação** — Java, Python, Shell, REST, Spring Boot, Git, Docker

---

## 🧬 Tiers de Modelos

| Tier | RAM Necessária | Modelo | Contexto | Visão |
|------|---------------|--------|----------|-------|
| 🔵 NANO | 4–6 GB | Gemma 3 1B | 131.072 tokens | ❌ |
| 🟢 FAST | 7–10 GB | Dolphin 3.0 Llama 3.1 8B | 8.192 tokens | ❌ |
| 🟡 SMART | 11–16 GB | Mistral Nemo 12B | 16.384 tokens | ✅ |
| 🟠 PREMIUM | 17–28 GB | Mistral Small 24B | 32.768 tokens | ✅ |
| 🔴 ULTRA | 32 GB+ | DeepSeek R1 Abliterated 32B | 65.536 tokens | ✅ |

---

## 🌐 Modo Web Bonus

Quando o sistema detecta conexão com a internet, **automaticamente e sem perguntar**:

1. Ativa o agente de busca DuckDuckGo no AnythingLLM
2. O modelo decide sozinho quando precisa buscar dados atuais
3. Busca, lê as páginas, injeta como contexto e responde
4. **Todo o processamento continua 100% local no seu drive**

Sem internet → funciona normalmente como IA local completa.
Com internet → equivalente ao Perplexity, mas rodando no seu hardware.

---

## 📦 Como instalar

### Requisitos
- Windows 10 ou 11 (64-bit)
- Pen Drive ou SSD com **mínimo 4GB livres** (recomendado 32GB+ para tier ULTRA)
- Conexão com internet apenas durante a instalação

### Passo a passo

**1.** Baixe o arquivo ZIP na aba [Releases](../../releases)

**2.** Extraia **na raiz** do Pen Drive ou SSD externo:
E:
├── install.bat
├── install-core.ps1
├── start-windows.bat
├── web_context.ps1
├── README.md
├── TUTORIAL.md
└── LICENSE

text

**3.** Execute o instalador:
Clique duplo em: install.bat

text

**4.** Aguarde os downloads (pode demorar 30 min a 2h dependendo do tier e internet)

**5.** Quando terminar, execute:
Clique duplo em: start-windows.bat

text

---

## 🖥️ Como usar

Após iniciar com `start-windows.bat`:

- A janela preta mostra o status do sistema
- O chat do AnythingLLM abre automaticamente
- Digite sua pergunta normalmente — jurídica, técnica, código, análise de imagem
- **Mantenha a janela preta aberta enquanto usa**
- Para desligar: pressione qualquer tecla na janela preta → ejeta o drive com segurança

---

## ⚖️ Casos de uso jurídico

A IA foi treinada com instruções específicas para o direito brasileiro:

- Redação de petições iniciais, recursos e contestações
- Análise de jurisprudência STJ, STF, TJMG e TRT
- Procedimentos PJe — protocolos, prazos e recursos
- Lei 9.099/95 — Juizados Especiais Cíveis e Criminais
- CLT — rescisão, FGTS, horas extras, assédio
- CDC — direitos do consumidor, inversão do ônus
- CPC — prazos processuais, nulidades, embargos

---

## 💻 Casos de uso em programação

- Revisão e geração de código Java, Python, Shell, Batch
- Spring Boot — APIs REST, Maven, microsserviços
- Git — commits, branches, conflitos, rebase
- Docker e Oracle Cloud — deploy, containers
- Debugging — análise de erros, stack traces
- Documentação técnica e comentários de código
- Scripts de automação e deploy CI/CD

---

## 🔒 Privacidade e segurança
┌─────────────────────────────────────────────────┐
│ O que NUNCA sai do seu drive: │
│ │
│ ✅ Suas perguntas e conversas │
│ ✅ Os documentos que você envia │
│ ✅ O modelo de IA │
│ ✅ O processamento das respostas │
│ │
│ O que pode sair (apenas no Web Bonus): │
│ 🌐 Apenas a query de busca (ex: "STJ 2025") │
│ vai para DuckDuckGo — igual a pesquisar │
│ no navegador. Zero dados pessoais. │
└─────────────────────────────────────────────────┘

text

---

## 📁 Estrutura do drive após instalação
drive:
├── install.bat ← Instalar (rodar uma vez)
├── install-core.ps1 ← Núcleo do instalador
├── start-windows.bat ← INICIAR (usar sempre)
├── web_context.ps1 ← Motor de Web Bonus
├── README.md
├── TUTORIAL.md
├── LICENSE
├── models\ ← Modelos de IA (arquivos .gguf)
├── ollama\ ← Motor Ollama portátil
├── anythingllm_app\ ← Interface de chat portátil
└── data\ ← Dados e configurações
├── anythingllm
├── ollama-profile
└── ollama-local

text

---

## ❓ Problemas comuns

**Modelo não encontrado:**
> Execute `install.bat` primeiro. O `start-windows.bat` só funciona após a instalação.

**AnythingLLM não abre:**
> Delete a pasta `anythingllm_app\` e rode `install.bat` novamente.

**Download travado:**
> Feche tudo, delete arquivos parciais na pasta `models\` e rode `install.bat` novamente.

**GPU não detectada:**
> O sistema usa CPU automaticamente como fallback. Funciona normalmente, porém mais lento.

**Windows bloqueou o .bat:**
> Clique com botão direito → Propriedades → Desbloquear → OK

---

## 📜 Licença

© 2026 WillTechBH — Todos os direitos reservados.
Este software é proprietário. Proibida reprodução, redistribuição ou uso comercial sem autorização.
Consulte o arquivo [LICENSE](LICENSE) para detalhes completos.

---

<div align="center">

**Desenvolvido por [WillTechBH](https://github.com/hebwil)**

*IA para quem precisa de resultado, não de assinatura.*

</div>
