[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OllamaExe,
    [Parameter(Mandatory = $true)]
    [string]$ModelsRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [string]$MainLlmModel = "qwen3.5:27b-q4_K_M",
    [string]$FallbackLlmModel = "qwen3.5:9b-q4_K_M",
    [string]$EmbeddingModel = "qwen3-embedding:0.6b",
    [int]$Port = 11435
)

$ErrorActionPreference = "Stop"
$ollama = (Resolve-Path -LiteralPath $OllamaExe).Path
$python = (Resolve-Path -LiteralPath $PythonExe).Path
if (Test-Path -LiteralPath $ModelsRoot) {
    throw "ModelsRoot already exists; use a new empty output path: $ModelsRoot"
}
if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Port must be between 1 and 65535"
}
New-Item -ItemType Directory -Path $ModelsRoot | Out-Null
$models = (Resolve-Path -LiteralPath $ModelsRoot).Path
$oldHost = $env:OLLAMA_HOST
$oldModels = $env:OLLAMA_MODELS
$env:OLLAMA_HOST = "127.0.0.1:$Port"
$env:OLLAMA_MODELS = $models
$process = $null
try {
    $process = Start-Process -FilePath $ollama -ArgumentList "serve" `
        -WindowStyle Hidden -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($process.HasExited) {
            throw "Ollama preparation service exited with code $($process.ExitCode)"
        }
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" `
                -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        throw "Ollama preparation service did not become ready"
    }
    foreach ($model in ($MainLlmModel, $FallbackLlmModel, $EmbeddingModel)) {
        & $ollama pull $model
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to pull Ollama model: $model"
        }
    }
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
    $env:OLLAMA_HOST = $oldHost
    $env:OLLAMA_MODELS = $oldModels
}

& $python (Join-Path $PSScriptRoot "ollama_model_store.py") $models `
    --required-model $MainLlmModel `
    --required-model $FallbackLlmModel `
    --required-model $EmbeddingModel
if ($LASTEXITCODE -ne 0) {
    throw "Prepared Ollama model store validation failed"
}
Write-Output "Ollama model store prepared: $models"
