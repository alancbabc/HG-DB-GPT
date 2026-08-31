[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [Parameter(Mandatory = $true)]
    [string]$RuntimeUserSid
)

$ErrorActionPreference = "Stop"
$common = Join-Path $PSScriptRoot "DBGPTOfflineSetup.Common.ps1"
. $common
$release = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$config = Get-DBGPTDeploymentConfig -ConfigPath $ConfigPath
$releaseVersion = Get-DBGPTReleaseVersion -ReleaseRoot $release
$resultRoot = Join-Path $config.dataRoot "install"
$resultPath = Join-Path $resultRoot "system-result.json"

function Write-SystemResult {
    param([bool]$Success, [string]$Message, [int]$ExitCode)
    New-Item -ItemType Directory -Force -Path $resultRoot | Out-Null
    [ordered]@{
        success = $Success
        releaseVersion = $releaseVersion
        message = $Message
        exitCode = $ExitCode
        completedAt = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )) {
        throw "Administrator permission is required"
    }

    Write-Host "[1/5] Checking disk, paths, and ports..."
    $preflightOutput = & (Join-Path $release "scripts\Test-DBGPTPreflight.ps1") `
        -ReleaseRoot $release -InstallRoot $config.installRoot `
        -DataRoot $config.dataRoot -ModelRoot $config.modelRoot `
        -WebPort $config.webPort -OllamaPort $config.ollamaPort
    if ($LASTEXITCODE -ne 0) {
        throw "Preflight failed: $($preflightOutput -join '`n')"
    }
    New-Item -ItemType Directory -Force -Path $resultRoot | Out-Null
    ($preflightOutput -join "`n") | Set-Content -LiteralPath (
        Join-Path $resultRoot "preflight.json"
    ) -Encoding UTF8

    Write-Host "[2/5] Verifying the release media..."
    $verificationOutput = & (Join-Path $release "scripts\Test-OfflineRelease.ps1") `
        -ReleaseRoot $release
    if ($LASTEXITCODE -ne 0) {
        throw "Release media verification failed"
    }
    ($verificationOutput -join "`n") | Set-Content -LiteralPath (
        Join-Path $resultRoot "release-verification.json"
    ) -Encoding UTF8

    Write-Host "[3/5] Installing Python, DB-GPT, and model files..."
    $installedPython = Join-Path $config.installRoot "python\python.exe"
    $runtimeCheck = Join-Path $config.installRoot `
        "scripts\check_installed_runtime.py"
    $modelCheck = Join-Path $config.installRoot `
        "scripts\ollama_model_store.py"
    $applicationReady = (Test-Path -LiteralPath $installedPython -PathType Leaf) `
        -and (Test-Path -LiteralPath $runtimeCheck -PathType Leaf) `
        -and (Test-Path -LiteralPath $modelCheck -PathType Leaf)
    if ($applicationReady) {
        & $installedPython $runtimeCheck
        $applicationReady = $LASTEXITCODE -eq 0
    }
    if ($applicationReady) {
        & $installedPython $modelCheck $config.modelRoot
        $applicationReady = $LASTEXITCODE -eq 0
    }
    if (-not $applicationReady) {
        $installArguments = @{
            ReleaseRoot = $release
            InstallRoot = $config.installRoot
            DataRoot = $config.dataRoot
            ModelRoot = $config.modelRoot
        }
        if (Test-Path -LiteralPath $config.installRoot -PathType Container) {
            $installArguments["Resume"] = $true
        }
        & (Join-Path $release "scripts\Install-DBGPTOffline.ps1") `
            @installArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime installation failed"
        }
        $installedPython = Join-Path $config.installRoot "python\python.exe"
    }
    else {
        Write-Host "The installed runtime already matches; skipping the copy."
    }

    Write-Host "[4/5] Installing and starting the Ollama service..."
    & (Join-Path $config.installRoot "scripts\Register-DBGPTServices.ps1") `
        -InstallRoot $config.installRoot -DataRoot $config.dataRoot `
        -ModelRoot $config.modelRoot -LlmModel $config.mainLlmModel `
        -FallbackLlmModel $config.fallbackLlmModel `
        -EmbeddingModel $config.embeddingModel `
        -ContextLength $config.contextLength -RuntimeUserSid $RuntimeUserSid `
        -SkipDesktopShortcuts -RepairExisting
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama service installation failed"
    }
    $service = Get-Service -Name "HGTechOllama" -ErrorAction Stop
    if ($service.Status -ne "Running") {
        Start-Service -Name "HGTechOllama"
    }
    $ready = $false
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $ready -and $stopwatch.Elapsed.TotalSeconds -lt 120) {
        try {
            $response = Invoke-RestMethod -Uri (
                "http://127.0.0.1:$($config.ollamaPort)/api/version"
            ) -TimeoutSec 5
            $ready = -not [string]::IsNullOrWhiteSpace([string]$response.version)
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        throw "Ollama did not start within 120 seconds"
    }

    Write-Host "[5/5] Testing both LLMs and the embedding model..."
    $runtimeLock = Get-Content -LiteralPath (
        Join-Path $config.installRoot "scripts\runtime-media.lock.json"
    ) -Raw | ConvertFrom-Json
    $ollamaVersion = [string](
        $runtimeLock.artifacts | Where-Object { $_.id -eq "ollama" }
    ).version
    $modelOutput = & $installedPython (
        Join-Path $config.installRoot "scripts\check_ollama_offline.py"
    ) --base-url "http://127.0.0.1:$($config.ollamaPort)" `
        --llm-model $config.mainLlmModel `
        --fallback-llm-model $config.fallbackLlmModel `
        --embedding-model $config.embeddingModel `
        --expected-version $ollamaVersion --timeout-seconds 120
    if ($LASTEXITCODE -ne 0) {
        throw "Local model validation failed: $($modelOutput -join '`n')"
    }
    ($modelOutput -join "`n") | Set-Content -LiteralPath (
        Join-Path $resultRoot "model-validation.json"
    ) -Encoding UTF8

    Write-SystemResult -Success $true -Message "Installation completed" -ExitCode 0
    exit 0
}
catch {
    $message = $_.Exception.Message
    $restartRequired = $message -match "restart is required"
    $code = if ($restartRequired) { 3010 } else { 1 }
    try {
        Write-SystemResult -Success $false -Message $message -ExitCode $code
    }
    catch {
        [Console]::Error.WriteLine($_.Exception.Message)
    }
    [Console]::Error.WriteLine($message)
    exit $code
}
