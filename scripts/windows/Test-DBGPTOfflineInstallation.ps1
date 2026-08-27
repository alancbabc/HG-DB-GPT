[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$ModelRoot,
    [string]$MainLlmModel = "qwen3.5:27b-q4_K_M",
    [string]$FallbackLlmModel = "qwen3.5:9b-q4_K_M",
    [string]$EmbeddingModel = "qwen3-embedding:0.6b",
    [string]$ExpectedOllamaVersion = "0.32.15",
    [int]$WebPort = 5670,
    [int]$OllamaPort = 11434,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 600,
    [switch]$RequirePhysicalNetworkDisconnected
)

$ErrorActionPreference = "Stop"
$errors = [System.Collections.Generic.List[string]]::new()
$checks = [ordered]@{}
$details = [ordered]@{}
$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$models = (Resolve-Path -LiteralPath $ModelRoot).Path
$python = Join-Path $install "python\python.exe"
$scripts = Join-Path $install "scripts"

foreach ($required in @(
    $python,
    (Join-Path $scripts "check_ollama_offline.py"),
    (Join-Path $scripts "ollama_model_store.py")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        $errors.Add("Missing installed file: $required")
    }
}

$serviceRunning = @{}
foreach ($serviceName in @("HGTechOllama", "HGTechDBGPT")) {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    $running = $null -ne $service -and $service.Status -eq "Running"
    $serviceRunning[$serviceName] = $running
    $checks["${serviceName}Running"] = $running
    if (-not $running) {
        $status = if ($null -eq $service) { "missing" } else { $service.Status }
        $errors.Add("Service is not running: $serviceName ($status)")
    }
}

if ($RequirePhysicalNetworkDisconnected) {
    $connected = @(Get-NetAdapter -Physical -ErrorAction Stop | Where-Object {
        $_.Status -eq "Up"
    })
    $checks["physicalNetworkDisconnected"] = $connected.Count -eq 0
    $details["connectedPhysicalAdapters"] = @($connected | Select-Object Name, InterfaceDescription)
    if ($connected.Count -ne 0) {
        $errors.Add("Physical network adapter is still connected")
    }
}

foreach ($endpoint in @(
    @{ Name = "web"; Service = "HGTechDBGPT"; Port = $WebPort; Url = "http://127.0.0.1:$WebPort/api/health" },
    @{ Name = "ollama"; Service = "HGTechOllama"; Port = $OllamaPort; Url = "http://127.0.0.1:$OllamaPort/api/version" }
)) {
    if (-not $serviceRunning[$endpoint.Service]) {
        $checks["$($endpoint.Name)Reachable"] = $false
        continue
    }
    $ready = $false
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    while (-not $ready -and $stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-RestMethod -Uri $endpoint.Url -TimeoutSec 5
            $ready = $true
            $details["$($endpoint.Name)Response"] = $response
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    $checks["$($endpoint.Name)Reachable"] = $ready
    if (-not $ready) {
        $errors.Add("Local endpoint did not become ready: $($endpoint.Url)")
        continue
    }
    if ($endpoint.Name -eq "web") {
        $webHealthy = $response.status -eq "ok"
        $checks["webHealthy"] = $webHealthy
        if (-not $webHealthy) {
            $errors.Add("DB-GPT health endpoint did not report status=ok")
        }
    }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $endpoint.Port `
        -ErrorAction SilentlyContinue)
    $external = @($listeners | Where-Object {
        $_.LocalAddress -notin @("127.0.0.1", "::1")
    })
    $loopbackOnly = $listeners.Count -gt 0 -and $external.Count -eq 0
    $checks["$($endpoint.Name)LoopbackOnly"] = $loopbackOnly
    if (-not $loopbackOnly) {
        $errors.Add("Endpoint is not restricted to loopback: $($endpoint.Name)")
    }
}

if ($errors.Count -eq 0) {
    $storeOutput = & $python (Join-Path $scripts "ollama_model_store.py") $models `
        --required-model $MainLlmModel `
        --required-model $FallbackLlmModel `
        --required-model $EmbeddingModel
    $storeExitCode = $LASTEXITCODE
    try {
        $details["modelStore"] = ($storeOutput -join "`n") | ConvertFrom-Json
    }
    catch {
        $errors.Add("Model store check returned invalid JSON")
    }
    $checks["modelStoreValid"] = $storeExitCode -eq 0
    if ($storeExitCode -ne 0) {
        $errors.Add("Model store validation failed")
    }

    $ollamaOutput = & $python (Join-Path $scripts "check_ollama_offline.py") `
        --base-url "http://127.0.0.1:$OllamaPort" `
        --llm-model $MainLlmModel `
        --fallback-llm-model $FallbackLlmModel `
        --embedding-model $EmbeddingModel `
        --expected-version $ExpectedOllamaVersion `
        --timeout-seconds $TimeoutSeconds
    $ollamaExitCode = $LASTEXITCODE
    try {
        $details["ollama"] = ($ollamaOutput -join "`n") | ConvertFrom-Json
    }
    catch {
        $errors.Add("Ollama functional check returned invalid JSON")
    }
    $checks["ollamaFunctional"] = $ollamaExitCode -eq 0
    if ($ollamaExitCode -ne 0) {
        $errors.Add("Ollama functional validation failed")
    }
}

$report = [ordered]@{
    success = $errors.Count -eq 0
    checkedAt = (Get-Date).ToUniversalTime().ToString("o")
    installRoot = $install
    modelRoot = $models
    checks = $checks
    details = $details
    errors = $errors
}
$report | ConvertTo-Json -Depth 10
if ($errors.Count -ne 0) {
    exit 1
}
