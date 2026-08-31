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
    [int]$ContextLength = 16384,
    [string]$RuntimeUserSid,
    [switch]$SkipDesktopShortcuts,
    [switch]$RepairExisting
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
$python = Join-Path $install "python\python.exe"
$config = Join-Path $install "config\dbgpt-windows-offline-ollama.toml"
$metadataTemplate = Join-Path $install "metadata-template"
$tiktokenCache = Join-Path $install "tiktoken-cache"
$tiktokenCacheFile = Join-Path $tiktokenCache "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
foreach ($required in ($nssm, $ollama, $python, $config, $tiktokenCacheFile)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required installed file is missing: $required"
    }
}
if (-not (Test-Path -LiteralPath $metadataTemplate -PathType Container)) {
    throw "Required metadata template is missing: $metadataTemplate"
}

if (-not $PSCmdlet.ShouldProcess($install, "Register Ollama service and DB-GPT desktop shortcuts")) {
    return
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator PowerShell is required"
}
$runtimeSid = if ([string]::IsNullOrWhiteSpace($RuntimeUserSid)) {
    $identity.User.Value
}
else {
    $RuntimeUserSid
}
if ($runtimeSid -notmatch "^S-1-5-21-(\d+-){3}\d+$") {
    throw "RuntimeUserSid is not a valid local or domain user SID"
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
$metadataRoot = Join-Path $DataRoot "metadata"
Get-ChildItem -LiteralPath $metadataTemplate -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($metadataTemplate.Length).TrimStart("\")
    $destination = Join-Path $metadataRoot $relative
    if (-not (Test-Path -LiteralPath $destination)) {
        New-Item -ItemType Directory -Force -Path (
            Split-Path -Parent $destination
        ) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destination
    }
}
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $install, "/grant", "*S-1-5-20:(OI)(CI)RX"
) -Description "Grant service read access to the installation"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $install, "/grant", "*$($runtimeSid):(OI)(CI)RX"
) -Description "Grant the installing user read access to the installation"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $DataRoot, "/grant", "*$($runtimeSid):(OI)(CI)M"
) -Description "Grant the installing user access to DB-GPT runtime data"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $ModelRoot, "/inheritance:r"
) -Description "Remove inherited permissions from the offline model store"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    $ModelRoot, "/grant:r", "*S-1-5-32-544:(OI)(CI)F",
    "*S-1-5-18:(OI)(CI)F", "*S-1-5-20:(OI)(CI)RX"
) -Description "Grant explicit read-only service access to the offline model store"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    (Join-Path $ModelRoot "*"), "/reset", "/T", "/C"
) -Description "Reset model descendants to inherit the protected root ACL"
Invoke-NativeCommand -FilePath "icacls.exe" -Arguments @(
    (Join-Path $DataRoot "logs\ollama"), "/grant", "*S-1-5-20:(OI)(CI)M"
) -Description "Grant Ollama log access"

$existingService = Get-Service -Name "HGTechOllama" -ErrorAction SilentlyContinue
if ($null -ne $existingService) {
    if (-not $RepairExisting) {
        throw "Service already exists: HGTechOllama"
    }
    $existingApplication = (& $nssm get "HGTechOllama" Application | `
        Select-Object -Last 1).Trim().Trim('"')
    if ($LASTEXITCODE -ne 0 -or `
        [IO.Path]::GetFullPath($existingApplication) -ne `
        [IO.Path]::GetFullPath($ollama)) {
        throw (
            "Existing HGTechOllama service belongs to another installation: " +
            $existingApplication
        )
    }
}
else {
    Invoke-NativeCommand $nssm @("install", "HGTechOllama", $ollama, "serve") `
        "Register the Ollama service"
}
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

if (-not $SkipDesktopShortcuts) {
    $shortcutInstaller = Join-Path $install `
        "scripts\Install-DBGPTDesktopShortcuts.ps1"
    & $shortcutInstaller -InstallRoot $install -DataRoot $DataRoot `
        -LlmModel $LlmModel -FallbackLlmModel $FallbackLlmModel `
        -EmbeddingModel $EmbeddingModel -ContextLength $ContextLength
}

Write-Output "Ollama service registration completed."
