[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
trap {
    try {
        Add-Type -AssemblyName PresentationFramework
        [Windows.MessageBox]::Show(
            $_.Exception.Message,
            "DB-GPT stop failed",
            [Windows.MessageBoxButton]::OK,
            [Windows.MessageBoxImage]::Error
        ) | Out-Null
    }
    catch {
        [Console]::Error.WriteLine($_.Exception.Message)
    }
    exit 1
}
$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$data = (Resolve-Path -LiteralPath $DataRoot).Path
$pidPath = Join-Path $data "run\dbgpt.pid"
$statePath = Join-Path $data "run\dbgpt-process.json"
if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    Write-Output "DB-GPT is not running (no PID file)."
    exit 0
}

$targetPid = 0
if (-not [int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$targetPid)) {
    throw "Invalid DB-GPT PID file: $pidPath"
}
$targetProcess = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if ($null -eq $targetProcess) {
    Remove-Item -LiteralPath $pidPath -Force
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    Write-Output "Removed a stale DB-GPT PID file."
    exit 0
}

$allowedPaths = @((Join-Path $install "python\python.exe"))
$actualPath = $targetProcess.Path
if ($actualPath -notin $allowedPaths) {
    throw "PID $targetPid does not belong to this DB-GPT installation: $actualPath"
}
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "DB-GPT process state is missing; refusing to stop PID $targetPid."
}
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ([int]$state.pid -ne $targetPid -or $state.installRoot -ne $install) {
    throw "DB-GPT process state does not match PID $targetPid and installation $install."
}

Stop-Process -Id $targetPid
$stopwatch = [Diagnostics.Stopwatch]::StartNew()
while ($null -ne (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) -and `
    $stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    Start-Sleep -Milliseconds 250
}
if ($null -ne (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {
    Stop-Process -Id $targetPid -Force
}
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
Write-Output "DB-GPT stopped."
exit 0
