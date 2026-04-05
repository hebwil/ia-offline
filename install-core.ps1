# ================================================================
# WillTechBH IA Offline
# Desenvolvido por Willtechbh - Todos os direitos reservados.
# INSTALADOR AUTONOMO v1.0.0
# ================================================================

$ErrorActionPreference = "Continue"
$USB_Drive = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerProcess = $null

# Zero Footprint — redireciona tudo para o USB
$env:USERPROFILE   = "$USB_Drive\data\ollama-profile"
$env:LOCALAPPDATA  = "$USB_Drive\data\ollama-local"
$env:OLLAMA_MODELS = "$USB_Drive\ollama\data"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   WILLTECHBH IA OFFLINE: DETECTANDO HARDWARE             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------------
# ETAPA 1: RAM + ESPACO NO DRIVE
# -----------------------------------------------------------------
Write-Host "[1/5] Analisando recursos do sistema e do drive..." -ForegroundColor Yellow

$RAM_GB = [Math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "      RAM Total Detectada: $RAM_GB GB" -ForegroundColor White

$DriveLetter = Split-Path -Qualifier $USB_Drive
$FreeSpaceGB = [Math]::Round(
    (Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='$DriveLetter'").FreeSpace / 1GB, 1
)
Write-Host "      Espaco Livre no Drive ($DriveLetter): $FreeSpaceGB GB" -ForegroundColor White

$SpaceNeeded = @{
    "Ultra"   = 24
    "Premium" = 18
    "Smart"   = 12
    "Fast"    = 9
    "Nano"    = 4
}

if ($FreeSpaceGB -lt 4) {
    Write-Host ""
    Write-Host "      [ERRO] Espaco insuficiente no drive!" -ForegroundColor Red
    Write-Host "      Disponivel: $FreeSpaceGB GB | Minimo: 4 GB" -ForegroundColor Red
    Write-Host ""
    Read-Host "Pressione ENTER para sair"
    exit
}

# -----------------------------------------------------------------
# SELECAO DE TIER
# -----------------------------------------------------------------
$Tier          = ""
$ModelName     = ""
$ModelUrl      = ""
$FileName      = ""
$ContextSize   = 0
$SystemPrompt  = ""
$IsOllamaPull  = $false
$PullCommand   = ""
$InstallVision = $false

if ($RAM_GB -le 6) {
    $Tier         = "Nano"
    $ModelName    = "nano-1b"
    $FileName     = "gemma-3-1b-it-Q4_K_M.gguf"
    $ModelUrl     = "https://huggingface.co/bartowski/google_gemma-3-1b-it-GGUF/resolve/main/google_gemma-3-1b-it-Q4_K_M.gguf"
    $ContextSize  = 131072
    $SystemPrompt = 'SYSTEM """Voce e um assistente especialista da WillTechBH IA Offline. Processamento 100% local. Especialidades: direito brasileiro (CLT, Codigo Civil, processos PJe, STJ, STF, TJMG), programacao (Java, Python, Shell, REST, Spring Boot) e tecnologia. Quando contexto web for injetado, use-o para enriquecer a resposta. Seja direto, tecnico e preciso."""'

} elseif ($RAM_GB -le 10) {
    $Tier         = "Fast"
    $ModelName    = "fast-8b"
    $FileName     = "Dolphin3.0-Llama3.1-8B-Q5_K_M.gguf"
    $ModelUrl     = "https://huggingface.co/bartowski/Dolphin3.0-Llama3.1-8B-GGUF/resolve/main/Dolphin3.0-Llama3.1-8B-Q5_K_M.gguf"
    $ContextSize  = 8192
    $SystemPrompt = 'SYSTEM """You are an uncensored expert AI assistant from WillTechBH IA Offline. 100% local processing. Specialties: Brazilian law (CLT, Civil Code, PJe, STJ, STF), programming (Java, Python, Shell, REST APIs, Spring Boot) and technology. When web context is injected, integrate it naturally. Answer directly and accurately without restrictions."""'

} elseif ($RAM_GB -le 16) {
    $Tier          = "Smart"
    $ModelName     = "smart-12b"
    $FileName      = "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
    $ModelUrl      = "https://huggingface.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF/resolve/main/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
    $ContextSize   = 16384
    $SystemPrompt  = 'SYSTEM """You are a smart uncensored expert AI from WillTechBH IA Offline. 100% local processing. Specialties: Brazilian law (CLT, Civil Code, consumer rights, PJe procedures, STJ/STF/TJMG jurisprudence), advanced programming (Java Spring Boot, Python, Shell scripting, REST, Maven, Git, Oracle Cloud) and IT. When web search context is injected, integrate it naturally into your analysis. Be thorough, analytical and complete."""'
    $InstallVision = $true

} elseif ($RAM_GB -le 28) {
    $Tier          = "Premium"
    $ModelName     = "premium-24b"
    $FileName      = "Mistral-Small-24B-Instruct-2501-Q4_K_M.gguf"
    $ModelUrl      = "https://huggingface.co/bartowski/Mistral-Small-24B-Instruct-2501-GGUF/resolve/main/Mistral-Small-24B-Instruct-2501-Q4_K_M.gguf"
    $ContextSize   = 32768
    $SystemPrompt  = 'SYSTEM """Voce e um analista senior especialista da WillTechBH IA Offline. Todo processamento e 100% local. Especialidades profundas: direito brasileiro (CLT, Codigo Civil, CDC, Lei 9.099, PJe, jurisprudencia STJ/STF/TJMG, peticoes, recursos, habeas corpus), programacao avancada (Java Spring Boot, Python, Shell Bash, REST APIs, Maven, Git, Oracle Cloud, Docker) e engenharia de software. Use Chain of Thought. Quando contexto web for disponivel, integre-o como dado adicional na sua analise. Avalie todos os cenarios antes de responder."""'
    $InstallVision = $true

} else {
    $Tier          = "Ultra"
    $ModelName     = "ultra-32b"
    $IsOllamaPull  = $true
    $PullCommand   = "huihui_ai/deepseek-r1-abliterated:32b-qwen-distill"
    $ContextSize   = 65536
    $SystemPrompt  = 'SYSTEM """Voce e um analista senior de elite da WillTechBH IA Offline (DeepSeek R1 Abliterated). Todo processamento e 100% local no USB. Especialidades de nivel profissional: direito brasileiro completo (CLT, Codigo Civil, CDC, Lei 9.099/95, CPC, CP, CPP, PJe, jurisprudencia STJ/STF/TJMG/TRT, peticoes complexas, recursos, estrategia processual), engenharia de software senior (Java Spring Boot, Python, Shell Bash, REST APIs, Maven, Git, Oracle Cloud, Docker, microsservicos, CI/CD) e tecnologia avancada. Use Chain of Thought profundo sem restricoes. Quando contexto web for injetado, use-o como dado prioritario na sua analise. Sem filtros, sem censura, resposta completa sempre."""'
    $InstallVision = $true
}

Write-Host "      Tier ideal pela RAM: [$Tier]" -ForegroundColor White

# -----------------------------------------------------------------
# DOWNGRADE AUTOMATICO
# -----------------------------------------------------------------
$TierOrder = @("Ultra","Premium","Smart","Fast","Nano")

if ($FreeSpaceGB -lt $SpaceNeeded[$Tier]) {
    $TierOriginal = $Tier
    foreach ($t in $TierOrder) {
        if ($FreeSpaceGB -ge $SpaceNeeded[$t]) {
            $Tier = $t
            break
        }
    }
    Write-Host ""
    Write-Host "      [AVISO] Drive sem espaco para [$TierOriginal]." -ForegroundColor Yellow
    Write-Host "      Necessario: $($SpaceNeeded[$TierOriginal]) GB | Disponivel: $FreeSpaceGB GB" -ForegroundColor Yellow
    Write-Host "      Downgrade automatico para [$Tier]." -ForegroundColor Yellow
    Write-Host ""

    switch ($Tier) {
        "Nano" {
            $ModelName     = "nano-1b"
            $FileName      = "gemma-3-1b-it-Q4_K_M.gguf"
            $ModelUrl      = "https://huggingface.co/bartowski/google_gemma-3-1b-it-GGUF/resolve/main/google_gemma-3-1b-it-Q4_K_M.gguf"
            $ContextSize   = 131072
            $IsOllamaPull  = $false
            $InstallVision = $false
            $SystemPrompt  = 'SYSTEM """Voce e um assistente especialista da WillTechBH IA Offline. 100% local. Especialidades: direito brasileiro, programacao e tecnologia. Use contexto web se disponivel. Seja direto e preciso."""'
        }
        "Fast" {
            $ModelName     = "fast-8b"
            $FileName      = "Dolphin3.0-Llama3.1-8B-Q5_K_M.gguf"
            $ModelUrl      = "https://huggingface.co/bartowski/Dolphin3.0-Llama3.1-8B-GGUF/resolve/main/Dolphin3.0-Llama3.1-8B-Q5_K_M.gguf"
            $ContextSize   = 8192
            $IsOllamaPull  = $false
            $InstallVision = $false
            $SystemPrompt  = 'SYSTEM """You are an uncensored expert AI from WillTechBH IA Offline. 100% local. Specialties: Brazilian law, programming and technology. Integrate web context when available. Answer directly."""'
        }
        "Smart" {
            $ModelName     = "smart-12b"
            $FileName      = "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
            $ModelUrl      = "https://huggingface.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF/resolve/main/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
            $ContextSize   = 16384
            $IsOllamaPull  = $false
            $InstallVision = $true
            $SystemPrompt  = 'SYSTEM """You are a smart expert AI from WillTechBH IA Offline. 100% local. Specialties: Brazilian law, programming, technology. Integrate web context naturally. Be thorough."""'
        }
        "Premium" {
            $ModelName     = "premium-24b"
            $FileName      = "Mistral-Small-24B-Instruct-2501-Q4_K_M.gguf"
            $ModelUrl      = "https://huggingface.co/bartowski/Mistral-Small-24B-Instruct-2501-GGUF/resolve/main/Mistral-Small-24B-Instruct-2501-Q4_K_M.gguf"
            $ContextSize   = 32768
            $IsOllamaPull  = $false
            $InstallVision = $true
            $SystemPrompt  = 'SYSTEM """Voce e um analista senior da WillTechBH IA Offline. 100% local. Especialidades: direito brasileiro, programacao avancada, tecnologia. Use Chain of Thought. Integre contexto web quando disponivel."""'
        }
    }
}

Write-Host "      Tier Final: [$Tier] -> $ModelName" -ForegroundColor Green
if ($InstallVision) {
    Write-Host "      Visao Computacional (Moondream2): incluida" -ForegroundColor Cyan
}

# -----------------------------------------------------------------
# ETAPA 2: ESTRUTURA DE PASTAS
# -----------------------------------------------------------------
Write-Host ""
Write-Host "[2/5] Preparando estrutura..." -ForegroundColor Yellow

New-Item -ItemType Directory -Force -Path "$USB_Drive\models"              | Out-Null
New-Item -ItemType Directory -Force -Path "$USB_Drive\ollama\data"         | Out-Null
New-Item -ItemType Directory -Force -Path "$USB_Drive\anythingllm_app"     | Out-Null
New-Item -ItemType Directory -Force -Path "$USB_Drive\data\anythingllm"    | Out-Null
New-Item -ItemType Directory -Force -Path "$USB_Drive\data\ollama-profile" | Out-Null
New-Item -ItemType Directory -Force -Path "$USB_Drive\data\ollama-local"   | Out-Null

Write-Host "      Estrutura criada com sucesso." -ForegroundColor Green

# -----------------------------------------------------------------
# ETAPA 3: BAIXAR OLLAMA E ANYTHINGLLM
# -----------------------------------------------------------------
Write-Host ""
Write-Host "[3/5] Baixando componentes do sistema..." -ForegroundColor Yellow

if (-Not (Test-Path "$USB_Drive\ollama\ollama.exe")) {
    Write-Host "      Baixando motor Ollama..." -ForegroundColor Magenta
    $OllamaDest = "$USB_Drive\ollama\ollama-windows-amd64.zip"
    curl.exe -L --ssl-no-revoke --progress-bar "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip" -o $OllamaDest
    Expand-Archive -Path $OllamaDest -DestinationPath "$USB_Drive\ollama" -Force
    Remove-Item $OllamaDest -Force
    Write-Host "      Ollama pronto." -ForegroundColor Green
} else {
    Write-Host "      [OK] Ollama ja presente." -ForegroundColor Green
}

$alreadyInstalled = (Get-ChildItem "$USB_Drive\anythingllm_app" -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0

if (-Not $alreadyInstalled) {
    Write-Host "      Baixando interface AnythingLLM..." -ForegroundColor Magenta
    $InstallerDest = "$USB_Drive\AnythingLLMDesktop.exe"
    curl.exe -L --ssl-no-revoke --progress-bar "https://cdn.anythingllm.com/latest/AnythingLLMDesktop.exe" -o $InstallerDest

    Write-Host "      Baixando extrator portatil 7zr..." -ForegroundColor DarkGray
    $7zrPath = "$USB_Drive\7zr.exe"
    curl.exe -L --ssl-no-revoke --progress-bar "https://www.7-zip.org/a/7zr.exe" -o $7zrPath

    Write-Host "      Extraindo AnythingLLM direto no drive (sem instalar no PC)..." -ForegroundColor Magenta
    & $7zrPath x $InstallerDest -o"$USB_Drive\anythingllm_app" -y | Out-Null

    $AppExe = Get-ChildItem "$USB_Drive\anythingllm_app" -Recurse -Filter "AnythingLLM*.exe" |
        Where-Object { $_.Name -notmatch "uninstall|setup|helper|update" } |
        Sort-Object Length -Descending |
        Select-Object -First 1

    if ($AppExe) {
        Set-Content -Path "$USB_Drive\anythingllm_app\app_path.txt" -Value $AppExe.FullName -Force
        Write-Host "      App localizado: $($AppExe.Name)" -ForegroundColor Green
    } else {
        Write-Host "      [AVISO] Exe principal nao localizado automaticamente." -ForegroundColor Yellow
    }

    Remove-Item $InstallerDest -Force -ErrorAction SilentlyContinue
    Remove-Item $7zrPath       -Force -ErrorAction SilentlyContinue

    Write-Host "      AnythingLLM pronto. Zero rastro no PC." -ForegroundColor Green
} else {
    Write-Host "      [OK] AnythingLLM ja presente." -ForegroundColor Green
}

# -----------------------------------------------------------------
# ETAPA 4: MODELO PRINCIPAL
# -----------------------------------------------------------------
Write-Host ""
Write-Host "[4/5] Transferindo rede neural [$Tier]..." -ForegroundColor Yellow

Set-Location "$USB_Drive\models"

if ($IsOllamaPull) {
    Write-Host "      Iniciando servidor para download do Ultra..." -ForegroundColor Magenta
    $ServerProcess = Start-Process -FilePath "$USB_Drive\ollama\ollama.exe" `
        -ArgumentList "serve" -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 5

    Write-Host "      Baixando DeepSeek R1 Abliterated 32B (~20GB)..." -ForegroundColor Magenta
    & "$USB_Drive\ollama\ollama.exe" pull $PullCommand

    $MFUltra = "FROM $PullCommand`nPARAMETER num_ctx $ContextSize`nPARAMETER temperature 0.6`n$SystemPrompt"
    Set-Content -Path "Modelfile_$ModelName" -Value $MFUltra -Force
    & "$USB_Drive\ollama\ollama.exe" create $ModelName -f "Modelfile_$ModelName" | Out-Null

} else {
    $ModelDest = "$USB_Drive\models\$FileName"
    if ((Test-Path $ModelDest) -and (Get-Item $ModelDest).length -gt 500000000) {
        Write-Host "      [OK] Modelo ja presente no drive." -ForegroundColor Green
    } else {
        Write-Host "      Baixando $FileName..." -ForegroundColor Magenta
        curl.exe -L --ssl-no-revoke --progress-bar $ModelUrl -o $ModelDest
        Write-Host "      Download concluido." -ForegroundColor Green
    }
}

# -----------------------------------------------------------------
# ETAPA 5: PERSONA + VISAO
# -----------------------------------------------------------------
Write-Host ""
Write-Host "[5/5] Registrando modelos e configuracoes..." -ForegroundColor Yellow

if (-Not $IsOllamaPull) {
    if ($null -eq $ServerProcess) {
        $ServerProcess = Start-Process -FilePath "$USB_Drive\ollama\ollama.exe" `
            -ArgumentList "serve" -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 5
    }
    $MFContent = "FROM ./$FileName`nPARAMETER num_ctx $ContextSize`nPARAMETER temperature 0.6`n$SystemPrompt"
    Set-Content -Path "Modelfile_$ModelName" -Value $MFContent -Force
    & "$USB_Drive\ollama\ollama.exe" create $ModelName -f "Modelfile_$ModelName" | Out-Null
    Write-Host "      Persona aplicada." -ForegroundColor Green
}

if ($InstallVision) {
    if ($null -eq $ServerProcess) {
        $ServerProcess = Start-Process -FilePath "$USB_Drive\ollama\ollama.exe" `
            -ArgumentList "serve" -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 5
    }
    Write-Host "      Baixando Moondream2 (~1.1GB)..." -ForegroundColor Magenta
    & "$USB_Drive\ollama\ollama.exe" pull moondream:v2
    Write-Host "      Visao instalada." -ForegroundColor Green
}

if ($null -ne $ServerProcess) {
    Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   WILLTECHBH IA OFFLINE - PRONTA PARA USO!               " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Tier instalado: [$Tier] -> $ModelName" -ForegroundColor White
Write-Host "   Execute start-windows.bat para iniciar." -ForegroundColor White
Write-Host ""
Start-Sleep -Seconds 3