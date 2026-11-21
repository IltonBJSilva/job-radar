# Gera um .zip do Job Radar para outra pessoa usar — SEM nenhum dado seu.
# (chamado por "Compartilhar Job Radar.bat"). Fica em dist\JobRadar-<data>.zip.
param([switch]$SemAbrir)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Dizer($texto, $cor = 'Cyan') { Write-Host $texto -ForegroundColor $cor }

# Dados pessoais: NUNCA vão no pacote, mesmo que o .gitignore mude um dia.
$proibidos = @(
    '^\.env$', '^config/candidato\.yaml', '^data/candidaturas\.db', '^data/perfil_ativo\.txt$',
    '^data/localidades\.json$', '^saida/', '^perfis/', '^venv/', '^\.venv/', '^dist/', '^\.agents/',
    '^curriculos_certificados/(?!\.gitkeep$)', '\.log$', '__pycache__/', '\.pyc$', '^\.pytest_cache/',
    '^rodar_diario\.cmd$', '^_to_delete/', '^\.git/'
)
function Proibido($caminho) {
    foreach ($p in $proibidos) { if ($caminho -match $p) { return $true } }
    return $false
}

# Lista de arquivos: o que o Git versiona + arquivos novos não ignorados.
$arquivos = @()
if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $raiz '.git'))) {
    $arquivos = git -c core.quotepath=off ls-files --cached --others --exclude-standard
} else {
    $arquivos = Get-ChildItem -Recurse -File | ForEach-Object {
        $_.FullName.Substring($raiz.Length + 1).Replace('\', '/')
    }
}
$arquivos = @($arquivos | Where-Object { $_ -and -not (Proibido $_) -and (Test-Path (Join-Path $raiz $_)) })

# Monta a pasta e compacta.
$temp = Join-Path $env:TEMP ("jobradar-pacote-" + [guid]::NewGuid().ToString('N'))
$pasta = Join-Path $temp 'JobRadar'
foreach ($a in $arquivos) {
    $destino = Join-Path $pasta $a
    New-Item -ItemType Directory -Force (Split-Path -Parent $destino) | Out-Null
    Copy-Item (Join-Path $raiz $a) $destino
}
@'
JOB RADAR — como começar
========================

1. Extraia esta pasta (botão direito no .zip -> "Extrair tudo...").
2. Dê dois cliques em "Iniciar Job Radar.bat".
   - Na primeira vez ele instala o que precisa (uns 5 minutos, precisa de internet).
   - Se o Windows avisar "O Windows protegeu o computador", clique em "Mais informações" -> "Executar assim mesmo".
3. O navegador abre sozinho. Envie seu currículo (PDF), escolha sua área e conecte seu Gmail.
4. Tudo começa em MODO SIMULAÇÃO: nada é enviado até você ligar o envio em Configurações.

Seus dados (currículo, e-mail, senha de app, vagas) ficam só no seu computador.
Mais detalhes no README.md.
'@ | Set-Content -Path (Join-Path $pasta 'LEIA-ME PRIMEIRO.txt') -Encoding UTF8

# Conferência final: nenhum arquivo pessoal entrou.
$vazou = Get-ChildItem $pasta -Recurse -File | Where-Object {
    Proibido ($_.FullName.Substring($pasta.Length + 1).Replace('\', '/'))
}
if ($vazou) {
    Remove-Item $temp -Recurse -Force
    throw "Arquivo pessoal no pacote, abortei: $($vazou.Name -join ', ')"
}
# Aviso extra: seu e-mail aparece em algum arquivo do pacote?
$meuEmail = ''
if (Test-Path (Join-Path $raiz '.env')) {
    $linha = Select-String -Path (Join-Path $raiz '.env') -Pattern '^SMTP_USUARIO=(.+)$' | Select-Object -First 1
    if ($linha) { $meuEmail = $linha.Matches[0].Groups[1].Value.Trim() }
}
if ($meuEmail) {
    $citam = Get-ChildItem $pasta -Recurse -File -Include *.py, *.md, *.yaml, *.yml, *.txt, *.html, *.json, *.env* |
        Select-String -SimpleMatch $meuEmail -List | ForEach-Object { $_.Path.Substring($pasta.Length + 1) }
    if ($citam) { Dizer "ATENÇÃO: seu e-mail aparece em: $($citam -join ', '). Confira antes de mandar." 'Yellow' }
}

New-Item -ItemType Directory -Force (Join-Path $raiz 'dist') | Out-Null
$zip = Join-Path $raiz ("dist\JobRadar-" + (Get-Date -Format 'yyyy-MM-dd') + '.zip')
if (Test-Path $zip) { Remove-Item $zip -Force }
# ZipArchive com "/" nos caminhos: o Compress-Archive do PowerShell 5.1 grava "\" e o .zip
# quebra fora do Explorer do Windows (7-Zip antigo, Mac, Linux).
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$fluxo = [IO.File]::Open($zip, [IO.FileMode]::Create)
$arquivoZip = New-Object IO.Compression.ZipArchive($fluxo, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($f in Get-ChildItem $pasta -Recurse -File) {
        $nome = 'JobRadar/' + $f.FullName.Substring($pasta.Length + 1).Replace('\', '/')
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($arquivoZip, $f.FullName, $nome,
            [IO.Compression.CompressionLevel]::Optimal)
    }
} finally {
    $arquivoZip.Dispose()
    $fluxo.Dispose()
}
Remove-Item $temp -Recurse -Force
$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Dizer "`nPronto: $zip ($($arquivos.Count) arquivos, $mb MB)" 'Green'
Dizer 'Sem currículo, e-mail, senha, vagas ou PDFs seus. Pode mandar para a pessoa.' 'Green'
if (-not $SemAbrir) { Start-Process explorer.exe "/select,`"$zip`"" }
