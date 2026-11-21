# Abre o Job Radar com dois cliques (chamado por "Iniciar Job Radar.bat").
# Na primeira vez: instala o Python (se faltar), cria o ambiente, instala as
# dependências e o navegador usado para gerar os PDFs. Depois: só abre.
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$Host.UI.RawUI.WindowTitle = 'Job Radar'
$url = 'http://127.0.0.1:5000'

function Dizer($texto, $cor = 'Cyan') { Write-Host $texto -ForegroundColor $cor }
function Falhar($texto) {
    Dizer "`n$texto" 'Red'
    Read-Host "`nAperte Enter para fechar"
    exit 1
}

Dizer "`n  JOB RADAR`n" 'White'

# Já está aberto? Só mostra no navegador.
try {
    Invoke-WebRequest "$url/" -UseBasicParsing -TimeoutSec 2 | Out-Null
    Dizer 'O Job Radar já está rodando. Abrindo o navegador...'
    Start-Process $url
    exit 0
} catch { }

# 1. Python 3.11 ou mais novo ---------------------------------------------------
function Achar-Python {
    $candidatos = @(
        @('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('python'), @('python3'),
        @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"),
        @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"),
        @("$env:ProgramFiles\Python313\python.exe"), @("$env:ProgramFiles\Python312\python.exe")
    )
    foreach ($c in $candidatos) {
        try {
            $extra = @($c | Select-Object -Skip 1)
            $ok = & $c[0] @extra -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
            if ($ok -eq 'True') { return , $c }
        } catch { }
    }
    return $null
}

$python = Achar-Python
if (-not $python) {
    Dizer 'Python não encontrado. Instalando o Python 3.12 (uma vez só, pode levar alguns minutos)...' 'Yellow'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
        $python = Achar-Python
    }
    if (-not $python) {
        Start-Process 'https://www.python.org/downloads/'
        Falhar ("Não consegui instalar o Python sozinho.`n" +
                "Baixe em python.org (a página foi aberta), instale marcando 'Add python.exe to PATH'`n" +
                "e depois dê dois cliques de novo em 'Iniciar Job Radar'.")
    }
}
$pyExtra = @($python | Select-Object -Skip 1)

# 2. Ambiente próprio (venv) ------------------------------------------------------
$venvPy = Join-Path $raiz 'venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Dizer 'Criando o ambiente do Job Radar...'
    & $python[0] @pyExtra -m venv venv
    if (-not (Test-Path $venvPy)) { Falhar 'Não consegui criar o ambiente (venv).' }
}

# 3. Dependências: só quando o requirements.txt mudou ----------------------------
$marca = Join-Path $raiz 'venv\.instalado'
$hash = (Get-FileHash (Join-Path $raiz 'requirements.txt') -Algorithm SHA256).Hash
$instalado = if (Test-Path $marca) { (Get-Content $marca -Raw).Trim() } else { '' }
if ($instalado -ne $hash) {
    Dizer 'Instalando as dependências (primeira vez: uns 3 a 5 minutos)...' 'Yellow'
    & $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
    & $venvPy -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Falhar 'Falhou a instalação das dependências. Confira a internet e tente de novo.' }
    Dizer 'Baixando o navegador usado para gerar os currículos em PDF...' 'Yellow'
    & $venvPy -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { Falhar 'Falhou o download do navegador (Chromium). Confira a internet e tente de novo.' }
    Set-Content -Path $marca -Value $hash -Encoding ASCII
}

# 4. Configuração inicial ------------------------------------------------------------
$env_ = Join-Path $raiz '.env'
if (-not (Test-Path $env_)) {
    Copy-Item (Join-Path $raiz '.env.example') $env_
    Dizer 'Criei o arquivo de configuração (.env) — tudo começa em modo simulação.'
}

# 5. Atalho na Área de Trabalho (uma vez) ----------------------------------------
try {
    $atalho = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Job Radar.lnk'
    if (-not (Test-Path $atalho)) {
        $s = (New-Object -ComObject WScript.Shell).CreateShortcut($atalho)
        $s.TargetPath = Join-Path $raiz 'Iniciar Job Radar.bat'
        $s.WorkingDirectory = $raiz
        $s.Description = 'Abre o Job Radar'
        $s.IconLocation = "$env:SystemRoot\System32\shell32.dll,22"
        $s.Save()
        Dizer 'Criei o atalho "Job Radar" na sua Área de Trabalho.'
    }
} catch { }

# 6. Abre ----------------------------------------------------------------------------
Dizer "`nAbrindo em $url ..." 'Green'
Dizer 'Deixe esta janela aberta enquanto usa. Para fechar o Job Radar, feche esta janela.' 'Gray'
& $venvPy candidatar.py app
