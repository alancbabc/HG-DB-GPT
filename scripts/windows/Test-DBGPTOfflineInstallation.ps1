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
    [string]$OllamaServiceName = "HGTechOllama",
    [string]$DBGPTServiceName = "HGTechDBGPT",
    [int]$WebPort = 5670,
    [int]$OllamaPort = 11434,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 600,
    [switch]$RequirePhysicalNetworkDisconnected,
    [switch]$RequireProcessNetworkIsolation
)

$ErrorActionPreference = "Stop"
$errors = [System.Collections.Generic.List[string]]::new()
$checks = [ordered]@{}
$details = [ordered]@{}
$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$models = (Resolve-Path -LiteralPath $ModelRoot).Path
$python = Join-Path $install "python\python.exe"
$scripts = Join-Path $install "scripts"
$tiktokenCache = Join-Path $install "tiktoken-cache"

foreach ($required in @(
    $python,
    (Join-Path $scripts "check_ollama_offline.py"),
    (Join-Path $scripts "check_tiktoken_offline.py"),
    (Join-Path $scripts "ollama_model_store.py"),
    (Join-Path $tiktokenCache "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"),
    (Join-Path $install "metadata-template\alembic\env.py")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        $errors.Add("Missing installed file: $required")
    }
}

$serviceRunning = @{}
foreach ($serviceName in @($OllamaServiceName, $DBGPTServiceName)) {
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

if ($RequireProcessNetworkIsolation) {
    $isolationScript = Join-Path $scripts "Set-DBGPTProcessNetworkIsolation.ps1"
    if (-not (Test-Path -LiteralPath $isolationScript -PathType Leaf)) {
        $checks["processNetworkIsolation"] = $false
        $errors.Add("Process network isolation script is missing")
    }
    else {
        $isolationOutput = & $isolationScript -InstallRoot $install -Action Status
        $isolationExitCode = $LASTEXITCODE
        try {
            $isolationReport = ($isolationOutput -join "`n") | ConvertFrom-Json
            $details["processNetworkIsolation"] = $isolationReport
            $isolationValid = $isolationExitCode -eq 0 -and `
                $isolationReport.success
            $checks["processNetworkIsolation"] = $isolationValid
            if (-not $isolationValid) {
                $errors.Add("Process network isolation is not active")
            }
        }
        catch {
            $checks["processNetworkIsolation"] = $false
            $errors.Add("Process network isolation check returned invalid JSON")
        }
    }
}

foreach ($endpoint in @(
    @{ Name = "web"; Service = $DBGPTServiceName; Port = $WebPort; Url = "http://127.0.0.1:$WebPort/api/health" },
    @{ Name = "ollama"; Service = $OllamaServiceName; Port = $OllamaPort; Url = "http://127.0.0.1:$OllamaPort/api/version" }
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
    if ($listeners.Count -eq 0) {
        $listeners = @(& "$env:SystemRoot\System32\netstat.exe" -ano -p tcp | `
            ForEach-Object {
                if ($_ -match (
                    "^\s*TCP\s+(\S+):" + $endpoint.Port +
                    "\s+\S+\s+LISTENING\s+(\d+)\s*$"
                )) {
                    [pscustomobject]@{
                        LocalAddress = $Matches[1].Trim("[", "]")
                        LocalPort = $endpoint.Port
                        OwningProcess = [int]$Matches[2]
                    }
                }
            })
    }
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
    $tiktokenOutput = & $python (Join-Path $scripts "check_tiktoken_offline.py") `
        --cache-dir $tiktokenCache
    $tiktokenExitCode = $LASTEXITCODE
    try {
        $details["tiktoken"] = ($tiktokenOutput -join "`n") | ConvertFrom-Json
    }
    catch {
        $errors.Add("Tokenizer offline check returned invalid JSON")
    }
    $checks["tiktokenOffline"] = $tiktokenExitCode -eq 0
    if ($tiktokenExitCode -ne 0) {
        $errors.Add("Tokenizer offline validation failed")
    }

    $modelStoreReadable = $true
    try {
        $null = Get-ChildItem -LiteralPath (Join-Path $models "manifests") `
            -ErrorAction Stop | Select-Object -First 1
    }
    catch {
        $modelStoreReadable = $false
    }
    if ($modelStoreReadable) {
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
    }
    else {
        $checks["modelStoreProtectedFromOperator"] = $true
        $details["modelStore"] = (
            "Direct model-store read is denied by ACL; validating through Ollama API"
        )
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
exit 0
