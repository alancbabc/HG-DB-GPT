[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DownloadsRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [string]$PythonExe = "python",
    [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"
$lockPath = Join-Path $PSScriptRoot "runtime-media.lock.json"
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
if ($lock.schemaVersion -ne 1) {
    throw "Unsupported runtime media lock schema"
}
if (Test-Path -LiteralPath $OutputRoot) {
    throw "OutputRoot already exists: $OutputRoot"
}
New-Item -ItemType Directory -Force -Path $DownloadsRoot | Out-Null
$downloads = (Resolve-Path -LiteralPath $DownloadsRoot).Path

foreach ($artifact in $lock.artifacts) {
    $destination = Join-Path $downloads $artifact.fileName
    if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
        if ($SkipDownload) {
            throw "Missing runtime artifact: $($artifact.fileName)"
        }
        Invoke-WebRequest -Uri $artifact.url -OutFile $destination
    }
}
& $PythonExe (Join-Path $PSScriptRoot "runtime_media.py") $downloads `
    --lock $lockPath
if ($LASTEXITCODE -ne 0) {
    throw "Runtime download verification failed"
}

$outputParent = Split-Path -Parent ([IO.Path]::GetFullPath($OutputRoot))
New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
$staging = Join-Path $outputParent ("." + [IO.Path]::GetFileName($OutputRoot) + "-" + [Guid]::NewGuid())
try {
    New-Item -ItemType Directory -Path $staging | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging "runtime") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging "tools") | Out-Null
    $byId = @{}
    foreach ($artifact in $lock.artifacts) {
        $byId[$artifact.id] = $artifact
    }
    Copy-Item -LiteralPath (Join-Path $downloads $byId.python.fileName) `
        -Destination (Join-Path $staging "runtime\python-installer.exe")
    Copy-Item -LiteralPath (Join-Path $downloads $byId.vcRedist.fileName) `
        -Destination (Join-Path $staging "runtime\vc-redist.x64.exe")

    $nssmExtract = Join-Path $staging "nssm-extract"
    Expand-Archive -LiteralPath (Join-Path $downloads $byId.nssm.fileName) `
        -DestinationPath $nssmExtract
    $nssmExe = Get-ChildItem -LiteralPath $nssmExtract -Recurse -File `
        -Filter "nssm.exe" | Where-Object { $_.Directory.Name -eq "win64" } `
        | Select-Object -First 1
    if ($null -eq $nssmExe) {
        throw "NSSM archive does not contain win64\nssm.exe"
    }
    Copy-Item -LiteralPath $nssmExe.FullName `
        -Destination (Join-Path $staging "tools\nssm.exe")
    Remove-Item -LiteralPath $nssmExtract -Recurse -Force

    $ollamaRoot = Join-Path $staging "ollama"
    Expand-Archive -LiteralPath (Join-Path $downloads $byId.ollama.fileName) `
        -DestinationPath $ollamaRoot
    $ollamaExe = Join-Path $ollamaRoot "ollama.exe"
    if (-not (Test-Path -LiteralPath $ollamaExe -PathType Leaf)) {
        throw "Ollama archive does not contain ollama.exe"
    }

    foreach ($signedFile in @(
        (Join-Path $staging "runtime\python-installer.exe"),
        (Join-Path $staging "runtime\vc-redist.x64.exe"),
        $ollamaExe
    )) {
        $signature = Get-AuthenticodeSignature -LiteralPath $signedFile
        if ($signature.Status -ne "Valid") {
            throw "Invalid Authenticode signature: $signedFile ($($signature.Status))"
        }
    }
    $nssmVersion = & (Join-Path $staging "tools\nssm.exe") version
    if ($nssmVersion -notmatch [regex]::Escape($byId.nssm.version)) {
        throw "Unexpected NSSM version: $nssmVersion"
    }
    $ollamaVersionOutput = (& $ollamaExe --version 2>&1) -join "`n"
    if ($ollamaVersionOutput -notmatch [regex]::Escape($byId.ollama.version)) {
        throw "Unexpected Ollama version: $ollamaVersionOutput"
    }
    Copy-Item -LiteralPath $lockPath `
        -Destination (Join-Path $staging "runtime-media.lock.json")
    Move-Item -LiteralPath $staging -Destination $OutputRoot
}
catch {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
    throw
}

Write-Output "Windows runtime media prepared at $OutputRoot"
