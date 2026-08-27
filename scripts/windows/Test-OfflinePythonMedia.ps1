[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MediaRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
$media = (Resolve-Path -LiteralPath $MediaRoot).Path
$pythonSource = (Resolve-Path -LiteralPath $PythonExe).Path
$appWheels = Get-ChildItem -LiteralPath (Join-Path $media "app-wheels") `
    -Filter "*.whl" -File | Select-Object -ExpandProperty FullName
if (-not $appWheels) {
    throw "No application wheels found"
}
$wheelhouse = Join-Path $media "wheelhouse"
$testRoot = Join-Path $env:TEMP ("dbgpt-offline-python-" + [Guid]::NewGuid())
try {
    & $pythonSource -m venv $testRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create isolated Python environment"
    }
    $python = Join-Path $testRoot "Scripts\python.exe"
    & $python -m pip install --no-index --find-links $wheelhouse @appWheels ollama
    if ($LASTEXITCODE -ne 0) {
        throw "Offline dependency installation failed"
    }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "Installed Python dependency consistency check failed"
    }
    & $python (Join-Path $PSScriptRoot "check_installed_runtime.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Installed runtime self-check failed"
    }
    Write-Output "Offline Python media installation passed."
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
exit 0
