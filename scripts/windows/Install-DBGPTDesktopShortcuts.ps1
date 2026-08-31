[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$LlmModel = "qwen3.5:27b-q4_K_M",
    [string]$FallbackLlmModel = "qwen3.5:9b-q4_K_M",
    [string]$EmbeddingModel = "qwen3-embedding:0.6b",
    [ValidateRange(2048, 131072)]
    [int]$ContextLength = 16384,
    [string]$DesktopPath
)

$ErrorActionPreference = "Stop"
$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$data = (Resolve-Path -LiteralPath $DataRoot).Path
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$startScript = Join-Path $install "scripts\Start-DBGPT.ps1"
$stopScript = Join-Path $install "scripts\Stop-DBGPT.ps1"
foreach ($required in ($powershell, $startScript, $stopScript)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required shortcut target is missing: $required"
    }
}
$desktop = if ([string]::IsNullOrWhiteSpace($DesktopPath)) {
    [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
}
else {
    (Resolve-Path -LiteralPath $DesktopPath).Path
}
if (-not $PSCmdlet.ShouldProcess($desktop, "Install DB-GPT desktop shortcuts")) {
    return
}

$shell = New-Object -ComObject WScript.Shell
$startName = "$([char]0x542f)$([char]0x52a8) DB-GPT.lnk"
$stopName = "$([char]0x505c)$([char]0x6b62) DB-GPT.lnk"
$startShortcut = $shell.CreateShortcut((Join-Path $desktop $startName))
$startShortcut.TargetPath = $powershell
$startShortcut.Arguments = (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
    "-File `"$startScript`" -InstallRoot `"$install`" -DataRoot `"$data`" " +
    "-LlmModel `"$LlmModel`" -FallbackLlmModel `"$FallbackLlmModel`" " +
    "-EmbeddingModel `"$EmbeddingModel`" -ContextLength $ContextLength -OpenBrowser"
)
$startShortcut.WorkingDirectory = $install
$startShortcut.Description = "Start DB-GPT as the current Windows user"
$startShortcut.Save()

$stopShortcut = $shell.CreateShortcut((Join-Path $desktop $stopName))
$stopShortcut.TargetPath = $powershell
$stopShortcut.Arguments = (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
    "-File `"$stopScript`" -InstallRoot `"$install`" -DataRoot `"$data`""
)
$stopShortcut.WorkingDirectory = $install
$stopShortcut.Description = "Stop the DB-GPT process from this installation"
$stopShortcut.Save()
Write-Output "DB-GPT desktop shortcuts installed for $([Security.Principal.WindowsIdentity]::GetCurrent().Name)."
