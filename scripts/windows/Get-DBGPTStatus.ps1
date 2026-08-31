[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [ValidateRange(1, 65535)]
    [int]$WebPort = 5670
)

$ErrorActionPreference = "Stop"
$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$data = (Resolve-Path -LiteralPath $DataRoot).Path
$pidPath = Join-Path $data "run\dbgpt.pid"
$statePath = Join-Path $data "run\dbgpt-process.json"
$targetPid = $null
$running = $false
$healthy = $false
$state = $null
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $parsedPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$parsedPid)) {
        $targetPid = $parsedPid
        $running = $null -ne (Get-Process -Id $parsedPid -ErrorAction SilentlyContinue)
    }
}
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    }
    catch {
        $state = $null
    }
}
if ($running) {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$WebPort/api/health" `
            -TimeoutSec 5
        $healthy = $response.status -eq "ok"
    }
    catch {
        $healthy = $false
    }
}
$report = [ordered]@{
    running = $running
    healthy = $healthy
    pid = $targetPid
    installRoot = $install
    dataRoot = $data
    recordedUser = if ($null -eq $state) { $null } else { $state.user }
    url = "http://127.0.0.1:$WebPort/"
}
$report | ConvertTo-Json
if (-not $healthy) {
    exit 1
}
exit 0
