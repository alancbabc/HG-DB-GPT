[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$ModelRoot
)

$ErrorActionPreference = "Stop"
$release = (Resolve-Path -LiteralPath $ReleaseRoot).Path
& (Join-Path $release "scripts\Test-OfflineRelease.ps1") -ReleaseRoot $release
if ($LASTEXITCODE -ne 0) {
    throw "Offline release verification failed"
}
if (Test-Path -LiteralPath $InstallRoot) {
    throw "InstallRoot already exists; use upgrade/rollback workflow: $InstallRoot"
}
if (-not $PSCmdlet.ShouldProcess($InstallRoot, "Install DB-GPT offline release")) {
    return
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator PowerShell is required"
}

New-Item -ItemType Directory -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DataRoot, $ModelRoot | Out-Null
$pythonRoot = Join-Path $InstallRoot "python"
$pythonInstaller = Join-Path $release "runtime\python-installer.exe"
$arguments = @(
    "/quiet",
    "InstallAllUsers=1",
    "TargetDir=$pythonRoot",
    "Include_pip=1",
    "Include_test=0",
    "PrependPath=0"
)
$process = Start-Process -FilePath $pythonInstaller -ArgumentList $arguments `
    -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Python installer failed with exit code $($process.ExitCode)"
}

$python = Join-Path $pythonRoot "python.exe"
$wheelhouse = Join-Path $release "wheelhouse"
$appWheels = Get-ChildItem -LiteralPath (Join-Path $release "app-wheels") `
    -Filter "*.whl" -File | Select-Object -ExpandProperty FullName
& $python -m pip install --no-index --find-links $wheelhouse @appWheels ollama
if ($LASTEXITCODE -ne 0) {
    throw "Offline Python dependency installation failed"
}
$runtimeCheck = Join-Path $release "scripts\check_installed_runtime.py"
& $python $runtimeCheck
if ($LASTEXITCODE -ne 0) {
    throw "Installed DB-GPT runtime self-check failed"
}

Copy-Item -LiteralPath (Join-Path $release "ollama") `
    -Destination (Join-Path $InstallRoot "ollama") -Recurse
Copy-Item -LiteralPath (Join-Path $release "tools") `
    -Destination (Join-Path $InstallRoot "tools") -Recurse
Copy-Item -LiteralPath (Join-Path $release "scripts") `
    -Destination (Join-Path $InstallRoot "scripts") -Recurse
Copy-Item -Path (Join-Path $release "models\*") `
    -Destination $ModelRoot -Recurse
New-Item -ItemType Directory -Path (Join-Path $InstallRoot "config") | Out-Null
Copy-Item -LiteralPath (
    Join-Path $release "config\dbgpt-windows-offline-ollama.example.toml"
) -Destination (
    Join-Path $InstallRoot "config\dbgpt-windows-offline-ollama.toml"
)
Copy-Item -LiteralPath (Join-Path $release "release-manifest.json") `
    -Destination (Join-Path $InstallRoot "release-manifest.json")

Write-Output "Offline files installed. Review paths and then register services."
