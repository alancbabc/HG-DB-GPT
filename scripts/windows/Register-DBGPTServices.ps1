[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$ModelRoot,
    [string]$LlmModel = "qwen3.5:27b-q4_K_M",
    [string]$FallbackLlmModel = "qwen3.5:9b-q4_K_M",
    [string]$EmbeddingModel = "qwen3-embedding:0.6b",
    [ValidateRange(2048, 131072)]
    [int]$ContextLength = 8192
)

$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )
    & $FilePath @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$nssm = Join-Path $install "tools\nssm.exe"
$ollama = Join-Path $install "ollama\ollama.exe"
$dbgpt = Join-Path $install "python\Scripts\dbgpt.exe"
$config = Join-Path $install "config\dbgpt-windows-offline-ollama.toml"
foreach ($required in ($nssm, $ollama, $dbgpt, $config)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required installed file is missing: $required"
    }
}

if (-not $PSCmdlet.ShouldProcess($install, "Register DB-GPT and Ollama services")) {
    return
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator PowerShell is required"
}

foreach ($serviceName in ("HGTechOllama", "HGTechDBGPT")) {
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        throw "Service already exists: $serviceName"
    }
}

$dataDirectories = @(
    $DataRoot,
    $ModelRoot,
    (Join-Path $DataRoot "metadata"),
    (Join-Path $DataRoot "vector_store"),
    (Join-Path $DataRoot "uploads"),
    (Join-Path $DataRoot "outputs"),
    (Join-Path $DataRoot "temp"),
    (Join-Path $DataRoot "backups"),
    (Join-Path $DataRoot "logs\dbgpt"),
    (Join-Path $DataRoot "logs\ollama")
)
New-Item -ItemType Directory -Force -Path $dataDirectories | Out-Null
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $install, "/grant", "*S-1-5-19:(OI)(CI)RX", "*S-1-5-20:(OI)(CI)RX"
) -Description "Grant service read access to the installation"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $DataRoot, "/grant", "*S-1-5-19:(OI)(CI)M"
) -Description "Grant LocalService access to DB-GPT data"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $ModelRoot, "/inheritance:r", "/grant:r", "*S-1-5-32-544:(OI)(CI)F",
    "*S-1-5-18:(OI)(CI)F", "*S-1-5-20:(OI)(CI)RX", "/T", "/C"
) -Description "Restrict the offline model store to read-only service access"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    (Join-Path $DataRoot "logs\ollama"), "/grant", "*S-1-5-20:(OI)(CI)M"
) -Description "Grant Ollama log access"

Invoke-NativeCommand $nssm @("install", "HGTechOllama", $ollama, "serve") `
    "Register the Ollama service"
Invoke-NativeCommand $nssm @(
    "set", "HGTechOllama", "AppDirectory", (Split-Path $ollama)
) "Set the Ollama working directory"
Invoke-NativeCommand $nssm @(
    "set", "HGTechOllama", "AppEnvironmentExtra",
    "OLLAMA_HOST=127.0.0.1:11434", "OLLAMA_MODELS=$ModelRoot",
    "OLLAMA_NO_CLOUD=1", "OLLAMA_MAX_LOADED_MODELS=1",
    "OLLAMA_NUM_PARALLEL=1", "OLLAMA_CONTEXT_LENGTH=$ContextLength"
) "Set the Ollama environment"
Invoke-NativeCommand $nssm @(
    "set", "HGTechOllama", "AppStdout", (Join-Path $DataRoot "logs\ollama\stdout.log")
) "Set the Ollama stdout log"
Invoke-NativeCommand $nssm @(
    "set", "HGTechOllama", "AppStderr", (Join-Path $DataRoot "logs\ollama\stderr.log")
) "Set the Ollama stderr log"
foreach ($setting in @(
    @("AppRotateFiles", "1"),
    @("AppRotateOnline", "1"),
    @("AppRotateBytes", "10485760")
)) {
    Invoke-NativeCommand $nssm @("set", "HGTechOllama", $setting[0], $setting[1]) `
        "Set Ollama $($setting[0])"
}
Invoke-NativeCommand "sc.exe" @(
    "config", "HGTechOllama", "obj=", "NT AUTHORITY\NetworkService"
) "Set the Ollama service account"
Invoke-NativeCommand "sc.exe" @(
    "config", "HGTechOllama", "start=", "delayed-auto"
) "Set Ollama delayed automatic start"

$randomBytes = New-Object byte[] 32
$randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomGenerator.GetBytes($randomBytes)
}
finally {
    $randomGenerator.Dispose()
}
$encryptKey = (([BitConverter]::ToString($randomBytes)) -replace "-", "").ToLowerInvariant()
Invoke-NativeCommand $nssm @(
    "install", "HGTechDBGPT", $dbgpt,
    "start webserver --yes --config `"$config`""
) "Register the DB-GPT service"
Invoke-NativeCommand $nssm @(
    "set", "HGTechDBGPT", "AppDirectory", $install
) "Set the DB-GPT working directory"
Invoke-NativeCommand $nssm @(
    "set", "HGTechDBGPT", "DependOnService", "HGTechOllama"
) "Set the DB-GPT service dependency"
Invoke-NativeCommand $nssm @(
    "set", "HGTechDBGPT", "AppEnvironmentExtra",
    "DBGPT_DATA_DIR=$DataRoot", "DBGPT_LLM_MODEL=$LlmModel",
    "DBGPT_FALLBACK_LLM_MODEL=$FallbackLlmModel",
    "DBGPT_EMBEDDING_MODEL=$EmbeddingModel", "DBGPT_ENCRYPT_KEY=$encryptKey"
) "Set the DB-GPT environment"
Invoke-NativeCommand $nssm @(
    "set", "HGTechDBGPT", "AppStdout", (Join-Path $DataRoot "logs\dbgpt\stdout.log")
) "Set the DB-GPT stdout log"
Invoke-NativeCommand $nssm @(
    "set", "HGTechDBGPT", "AppStderr", (Join-Path $DataRoot "logs\dbgpt\stderr.log")
) "Set the DB-GPT stderr log"
foreach ($setting in @(
    @("AppRotateFiles", "1"),
    @("AppRotateOnline", "1"),
    @("AppRotateBytes", "10485760")
)) {
    Invoke-NativeCommand $nssm @("set", "HGTechDBGPT", $setting[0], $setting[1]) `
        "Set DB-GPT $($setting[0])"
}
Invoke-NativeCommand "sc.exe" @(
    "config", "HGTechDBGPT", "obj=", "NT AUTHORITY\LocalService"
) "Set the DB-GPT service account"
Invoke-NativeCommand "sc.exe" @(
    "config", "HGTechDBGPT", "start=", "delayed-auto"
) "Set DB-GPT delayed automatic start"

Write-Output "Services registered. Production database ACL must be configured separately."
