[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$LlmModel = "qwen3.5:27b-q4_K_M",
    [string]$FallbackLlmModel = "qwen3.5:9b-q4_K_M",
    [string]$EmbeddingModel = "qwen3-embedding:0.6b",
    [ValidateRange(2048, 131072)]
    [int]$ContextLength = 16384,
    [ValidateRange(1, 65535)]
    [int]$WebPort = 5670,
    [ValidateRange(1, 600)]
    [int]$StartupTimeoutSeconds = 120,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
trap {
    try {
        Add-Type -AssemblyName PresentationFramework
        [Windows.MessageBox]::Show(
            $_.Exception.Message,
            "DB-GPT startup failed",
            [Windows.MessageBoxButton]::OK,
            [Windows.MessageBoxImage]::Error
        ) | Out-Null
    }
    catch {
        [Console]::Error.WriteLine($_.Exception.Message)
    }
    exit 1
}

function Get-DBGPTEncryptKey {
    param([Parameter(Mandatory = $true)][string]$RuntimeRoot)

    $configRoot = Join-Path $RuntimeRoot "config"
    New-Item -ItemType Directory -Force -Path $configRoot | Out-Null
    $keyPath = Join-Path $configRoot "encrypt.key"
    if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
        $existingKey = (Get-Content -LiteralPath $keyPath -Raw).Trim()
        if ($existingKey -notmatch "^[0-9a-fA-F]{64}$") {
            throw "The persisted DB-GPT encryption key is invalid: $keyPath"
        }
        return $existingKey.ToLowerInvariant()
    }

    $keyBytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($keyBytes)
    }
    finally {
        $generator.Dispose()
    }
    $newKey = (([BitConverter]::ToString($keyBytes)) -replace "-", "").ToLowerInvariant()
    [IO.File]::WriteAllText($keyPath, $newKey)
    return $newKey
}

function Rotate-DBGPTLog {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -lt 10MB) {
        return
    }
    $archive = "$Path.$((Get-Date).ToString('yyyyMMddHHmmss'))"
    Move-Item -LiteralPath $Path -Destination $archive
}

$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$data = (Resolve-Path -LiteralPath $DataRoot -ErrorAction SilentlyContinue)
if ($null -eq $data) {
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    $data = Resolve-Path -LiteralPath $DataRoot
}
$data = $data.Path
$python = Join-Path $install "python\python.exe"
$config = Join-Path $install "config\dbgpt-windows-offline-ollama.toml"
$tiktokenCache = Join-Path $install "tiktoken-cache"
$ollamaService = Get-Service -Name "HGTechOllama" -ErrorAction SilentlyContinue
foreach ($required in ($python, $config, $tiktokenCache)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required installed path is missing: $required"
    }
}
if ($null -eq $ollamaService -or $ollamaService.Status -ne "Running") {
    throw "HGTechOllama is not running. Start the Ollama Windows service as an administrator and retry."
}

$runRoot = Join-Path $data "run"
$logRoot = Join-Path $data "logs\dbgpt"
New-Item -ItemType Directory -Force -Path $runRoot, $logRoot | Out-Null
$pidPath = Join-Path $runRoot "dbgpt.pid"
$statePath = Join-Path $runRoot "dbgpt-process.json"
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $existingPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$existingPid)) {
        $existing = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            if ($existing.Path -ne $python -or `
                -not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
                throw "PID $existingPid does not belong to the recorded DB-GPT installation. Stop it manually before retrying."
            }
            $existingState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            if ([int]$existingState.pid -ne $existingPid -or `
                $existingState.installRoot -ne $install) {
                throw "The recorded DB-GPT process state does not match PID $existingPid."
            }
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/api/health" `
                    -TimeoutSec 5
                if ($health.status -eq "ok") {
                    if ($OpenBrowser) {
                        Start-Process "http://127.0.0.1:$WebPort/" `
                            -ErrorAction SilentlyContinue
                    }
                    Write-Output "DB-GPT is already running with PID $existingPid."
                    exit 0
                }
            }
            catch {
                throw "A DB-GPT process is already recorded with PID $existingPid, but its health endpoint is unavailable. Stop it before retrying."
            }
        }
    }
    Remove-Item -LiteralPath $pidPath -Force
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
}

$listener = @(& "$env:SystemRoot\System32\netstat.exe" -ano -p tcp | Where-Object {
    $_ -match "^\s*TCP\s+\S+:$WebPort\s+\S+\s+LISTENING\s+\d+\s*$"
})
if ($listener.Count -gt 0) {
    throw "TCP port $WebPort is already in use. Refusing to start a second DB-GPT instance."
}

$stdout = Join-Path $logRoot "stdout.log"
$stderr = Join-Path $logRoot "stderr.log"
Rotate-DBGPTLog -Path $stdout
Rotate-DBGPTLog -Path $stderr

$env:DBGPT_DATA_DIR = $data
$env:DBGPT_LLM_MODEL = $LlmModel
$env:DBGPT_FALLBACK_LLM_MODEL = $FallbackLlmModel
$env:DBGPT_EMBEDDING_MODEL = $EmbeddingModel
$env:DBGPT_CONTEXT_LENGTH = [string]$ContextLength
$env:DBGPT_ENCRYPT_KEY = Get-DBGPTEncryptKey -RuntimeRoot $data
$env:TIKTOKEN_CACHE_DIR = $tiktokenCache
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$arguments = @(
    "-m",
    "dbgpt.cli.cli_scripts",
    "start",
    "webserver",
    "--yes",
    "--config",
    "`"$config`""
)
$dbgptProcess = Start-Process -FilePath $python -ArgumentList $arguments `
    -WorkingDirectory $install -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
[IO.File]::WriteAllText($pidPath, [string]$dbgptProcess.Id)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$state = [ordered]@{
    pid = $dbgptProcess.Id
    user = $identity.Name
    userSid = $identity.User.Value
    installRoot = $install
    dataRoot = $data
    startedAt = (Get-Date).ToUniversalTime().ToString("o")
}
$state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

$ready = $false
$stopwatch = [Diagnostics.Stopwatch]::StartNew()
while (-not $ready -and $stopwatch.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds) {
    if ($dbgptProcess.HasExited) {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        throw "DB-GPT exited during startup with code $($dbgptProcess.ExitCode). Check $stderr"
    }
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/api/health" `
            -TimeoutSec 5
        $ready = $response.status -eq "ok"
    }
    catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Stop-Process -Id $dbgptProcess.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    throw "DB-GPT did not become healthy within $StartupTimeoutSeconds seconds. Check $stderr"
}
if ($OpenBrowser) {
    Start-Process "http://127.0.0.1:$WebPort/" -ErrorAction SilentlyContinue
}
Write-Output "DB-GPT is running as $($identity.Name) with PID $($dbgptProcess.Id)."
exit 0
