[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot
)

$ErrorActionPreference = "Stop"
$python = Join-Path $InstallRoot "python\python.exe"
$tool = Join-Path $InstallRoot "scripts\runtime_data.py"
foreach ($required in ($python, $tool, $DataRoot)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path is missing: $required"
    }
}
if (-not $PSCmdlet.ShouldProcess($DataRoot, "Stop DB-GPT and create backup")) {
    return
}

$service = Get-Service -Name "HGTechDBGPT" -ErrorAction SilentlyContinue
if (-not $service) {
    throw "HGTechDBGPT service is not installed; cannot guarantee a consistent backup"
}
$restart = $service.Status -ne "Stopped"
try {
    if ($restart) {
        Stop-Service -Name "HGTechDBGPT" -Force
        (Get-Service -Name "HGTechDBGPT").WaitForStatus("Stopped", "00:01:00")
    }
    & $python $tool backup $DataRoot $BackupRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime-data backup failed"
    }
}
finally {
    if ($restart) {
        Start-Service -Name "HGTechDBGPT"
    }
}
