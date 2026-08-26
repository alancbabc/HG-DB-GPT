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
& icacls $install /grant '*S-1-5-19:(OI)(CI)RX' '*S-1-5-20:(OI)(CI)RX' | Out-Null
& icacls $DataRoot /grant '*S-1-5-19:(OI)(CI)M' | Out-Null
& icacls $ModelRoot /grant '*S-1-5-20:(OI)(CI)M' | Out-Null
& icacls (Join-Path $DataRoot "logs\ollama") `
    /grant '*S-1-5-20:(OI)(CI)M' | Out-Null

& $nssm install HGTechOllama $ollama "serve"
& $nssm set HGTechOllama AppDirectory (Split-Path $ollama)
& $nssm set HGTechOllama AppEnvironmentExtra `
    "OLLAMA_HOST=127.0.0.1:11434" "OLLAMA_MODELS=$ModelRoot" `
    "OLLAMA_NO_CLOUD=1" "OLLAMA_MAX_LOADED_MODELS=1" `
    "OLLAMA_NUM_PARALLEL=1" "OLLAMA_CONTEXT_LENGTH=$ContextLength"
& $nssm set HGTechOllama AppStdout (Join-Path $DataRoot "logs\ollama\stdout.log")
& $nssm set HGTechOllama AppStderr (Join-Path $DataRoot "logs\ollama\stderr.log")
& $nssm set HGTechOllama AppRotateFiles 1
& $nssm set HGTechOllama AppRotateOnline 1
& $nssm set HGTechOllama AppRotateBytes 10485760
& sc.exe config HGTechOllama obj= "NT AUTHORITY\NetworkService" | Out-Null
& sc.exe config HGTechOllama start= delayed-auto | Out-Null

$randomBytes = New-Object byte[] 32
$randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomGenerator.GetBytes($randomBytes)
}
finally {
    $randomGenerator.Dispose()
}
$encryptKey = (([BitConverter]::ToString($randomBytes)) -replace "-", "").ToLowerInvariant()
& $nssm install HGTechDBGPT $dbgpt "start webserver --yes --config `"$config`""
& $nssm set HGTechDBGPT AppDirectory $install
& $nssm set HGTechDBGPT DependOnService HGTechOllama
& $nssm set HGTechDBGPT AppEnvironmentExtra `
    "DBGPT_DATA_DIR=$DataRoot" "DBGPT_LLM_MODEL=$LlmModel" `
    "DBGPT_FALLBACK_LLM_MODEL=$FallbackLlmModel" `
    "DBGPT_EMBEDDING_MODEL=$EmbeddingModel" "DBGPT_ENCRYPT_KEY=$encryptKey"
& $nssm set HGTechDBGPT AppStdout (Join-Path $DataRoot "logs\dbgpt\stdout.log")
& $nssm set HGTechDBGPT AppStderr (Join-Path $DataRoot "logs\dbgpt\stderr.log")
& $nssm set HGTechDBGPT AppRotateFiles 1
& $nssm set HGTechDBGPT AppRotateOnline 1
& $nssm set HGTechDBGPT AppRotateBytes 10485760
& sc.exe config HGTechDBGPT obj= "NT AUTHORITY\LocalService" | Out-Null
& sc.exe config HGTechDBGPT start= delayed-auto | Out-Null

Write-Output "Services registered. Production database ACL must be configured separately."
