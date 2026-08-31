[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot,
    [Parameter(Mandatory = $true)]
    [string]$NewDataRoot
)

$ErrorActionPreference = "Stop"
$python = Join-Path $InstallRoot "python\python.exe"
$tool = Join-Path $InstallRoot "scripts\runtime_data.py"
foreach ($required in ($python, $tool, $BackupRoot)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path is missing: $required"
    }
}
if (Test-Path -LiteralPath $NewDataRoot) {
    throw "Restore destination already exists: $NewDataRoot"
}
if (-not $PSCmdlet.ShouldProcess($NewDataRoot, "Restore verified backup to new root")) {
    return
}

& $python $tool restore $BackupRoot $NewDataRoot
if ($LASTEXITCODE -ne 0) {
    throw "Runtime-data restore failed"
}
Write-Output "Restore completed for the current Windows user without replacing the current data root."
