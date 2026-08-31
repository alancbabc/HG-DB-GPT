[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$ModelRoot,
    [string]$MainLlmModel = "qwen3.5:27b-q4_K_M",
    [string]$FallbackLlmModel = "qwen3.5:9b-q4_K_M",
    [string]$EmbeddingModel = "qwen3-embedding:0.6b",
    [string]$ExpectedOllamaVersion = "0.32.15",
    [string]$OllamaServiceName = "HGTechOllama",
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
$data = (Resolve-Path -LiteralPath $DataRoot).Path
$models = (Resolve-Path -LiteralPath $ModelRoot).Path
$python = Join-Path $install "python\python.exe"
$scripts = Join-Path $install "scripts"
$tiktokenCache = Join-Path $install "tiktoken-cache"
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$startShortcutName = "$([char]0x542f)$([char]0x52a8) DB-GPT.lnk"
$stopShortcutName = "$([char]0x505c)$([char]0x6b62) DB-GPT.lnk"

foreach ($required in @(
    $python,
    (Join-Path $scripts "check_ollama_offline.py"),
    (Join-Path $scripts "check_tiktoken_offline.py"),
    (Join-Path $scripts "ollama_model_store.py"),
    (Join-Path $scripts "Start-DBGPT.ps1"),
    (Join-Path $scripts "Stop-DBGPT.ps1"),
    (Join-Path $tiktokenCache "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"),
    (Join-Path $install "metadata-template\alembic\env.py")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        $errors.Add("Missing installed file: $required")
    }
}

$startShortcutInstalled = Test-Path -LiteralPath (
    Join-Path $desktop $startShortcutName
) -PathType Leaf
$stopShortcutInstalled = Test-Path -LiteralPath (
    Join-Path $desktop $stopShortcutName
) -PathType Leaf
$checks["startShortcutInstalled"] = $startShortcutInstalled
$checks["stopShortcutInstalled"] = $stopShortcutInstalled
if (-not $startShortcutInstalled -or -not $stopShortcutInstalled) {
    $errors.Add("DB-GPT desktop shortcuts are missing for the current Windows user")
}

$ollamaService = Get-Service -Name $OllamaServiceName -ErrorAction SilentlyContinue
$ollamaRunning = $null -ne $ollamaService -and $ollamaService.Status -eq "Running"
$checks["${OllamaServiceName}Running"] = $ollamaRunning
if (-not $ollamaRunning) {
    $status = if ($null -eq $ollamaService) { "missing" } else { $ollamaService.Status }
    $errors.Add("Service is not running: $OllamaServiceName ($status)")
}

$legacyService = Get-Service -Name "HGTechDBGPT" -ErrorAction SilentlyContinue
$legacyServiceInactive = $null -eq $legacyService -or $legacyService.Status -eq "Stopped"
$checks["legacyDBGPTServiceInactive"] = $legacyServiceInactive
if (-not $legacyServiceInactive) {
    $errors.Add("Legacy HGTechDBGPT LocalService instance is still running")
}

$pidPath = Join-Path $data "run\dbgpt.pid"
$statePath = Join-Path $data "run\dbgpt-process.json"
$dbgptRunning = $false
$dbgptRunsAsCurrentUser = $false
$dbgptRunsNonElevated = $false
$dbgptPid = $null
$recordedState = $null
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $parsedPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$parsedPid)) {
        $dbgptPid = $parsedPid
        $dbgptProcess = Get-Process -Id $parsedPid -ErrorAction SilentlyContinue
        $dbgptRunning = $null -ne $dbgptProcess
        if ($dbgptRunning) {
            if (Test-Path -LiteralPath $statePath -PathType Leaf) {
                try {
                    $recordedState = Get-Content -LiteralPath $statePath -Raw | `
                        ConvertFrom-Json
                }
                catch {
                    $recordedState = $null
                }
            }
            $stateMatchesProcess = $null -ne $recordedState -and `
                [int]$recordedState.pid -eq $parsedPid -and `
                $recordedState.installRoot -eq $install -and `
                $recordedState.dataRoot -eq $data -and `
                -not [string]::IsNullOrWhiteSpace($recordedState.user) -and `
                $recordedState.user -notin @(
                    "NT AUTHORITY\LOCAL SERVICE",
                    "NT AUTHORITY\SYSTEM"
                )
            if ($null -ne $recordedState) {
                $details["dbgptRecordedOwner"] = $recordedState.user
                $details["dbgptRecordedElevated"] = $recordedState.elevated
                $dbgptRunsNonElevated = $recordedState.elevated -eq $false
            }
            try {
                $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$parsedPid"
                $owner = Invoke-CimMethod -InputObject $processInfo -MethodName GetOwner
                $actualOwner = "$($owner.Domain)\$($owner.User)"
                $dbgptRunsAsCurrentUser = $stateMatchesProcess -and `
                    $actualOwner -ieq $recordedState.user
                $details["dbgptProcessOwner"] = $actualOwner
            }
            catch {
                $details["dbgptProcessOwner"] = if ($null -eq $recordedState) {
                    $null
                } else {
                    $recordedState.user
                }
                $details["dbgptOwnerVerification"] = (
                    "CIM owner lookup unavailable; validated launcher state, PID, " +
                    "installation and non-service account"
                )
                $dbgptRunsAsCurrentUser = $stateMatchesProcess
            }
        }
    }
}
$checks["dbgptProcessRunning"] = $dbgptRunning
$checks["dbgptRunsAsCurrentUser"] = $dbgptRunsAsCurrentUser
$checks["dbgptRunsNonElevated"] = $dbgptRunsNonElevated
$details["dbgptPid"] = $dbgptPid
if (-not $dbgptRunning) {
    $errors.Add("Current-user DB-GPT process is not running")
}
elseif (-not $dbgptRunsAsCurrentUser) {
    $errors.Add("DB-GPT is not running as the current Windows user")
}
elseif (-not $dbgptRunsNonElevated) {
    $errors.Add("DB-GPT was started with an elevated administrator token")
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
    @{ Name = "web"; RequiredProcessRunning = $dbgptRunning; Port = $WebPort; Url = "http://127.0.0.1:$WebPort/api/health" },
    @{ Name = "ollama"; RequiredProcessRunning = $ollamaRunning; Port = $OllamaPort; Url = "http://127.0.0.1:$OllamaPort/api/version" }
)) {
    if (-not $endpoint.RequiredProcessRunning) {
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
    dataRoot = $data
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
