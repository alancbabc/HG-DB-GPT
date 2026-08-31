[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$BackupRoot,
    [ValidateRange(1, 65535)]
    [int]$WebPort = 5670
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

$pidPath = Join-Path $DataRoot "run\dbgpt.pid"
$restart = $false
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $targetPid = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$targetPid)) {
        throw "Invalid DB-GPT PID file; cannot guarantee a consistent backup: $pidPath"
    }
    $restart = $null -ne (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)
    if (-not $restart) {
        & (Join-Path $InstallRoot "scripts\Stop-DBGPT.ps1") `
            -InstallRoot $InstallRoot -DataRoot $DataRoot
    }
}
if (-not $restart) {
    $listener = @(& "$env:SystemRoot\System32\netstat.exe" -ano -p tcp | Where-Object {
        $_ -match "^\s*TCP\s+\S+:$WebPort\s+\S+\s+LISTENING\s+\d+\s*$"
    })
    if ($listener.Count -gt 0) {
        throw "TCP port $WebPort is in use without a valid DB-GPT PID record; refusing an inconsistent backup."
    }
}
try {
    if ($restart) {
        & (Join-Path $InstallRoot "scripts\Stop-DBGPT.ps1") `
            -InstallRoot $InstallRoot -DataRoot $DataRoot
    }
    & $python $tool backup $DataRoot $BackupRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime-data backup failed"
    }
}
finally {
    if ($restart) {
        & (Join-Path $InstallRoot "scripts\Start-DBGPT.ps1") `
            -InstallRoot $InstallRoot -DataRoot $DataRoot
    }
}
