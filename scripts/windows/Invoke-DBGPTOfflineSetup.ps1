[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [string]$ConfigPath
)

$ErrorActionPreference = "Stop"
$release = (Resolve-Path -LiteralPath $ReleaseRoot).Path
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $localConfigPath = Join-Path $release "deployment-config.local.json"
    $ConfigPath = if (Test-Path -LiteralPath $localConfigPath -PathType Leaf) {
        $localConfigPath
    }
    else {
        Join-Path $release "deployment-config.json"
    }
}
$common = Join-Path $release "scripts\DBGPTOfflineSetup.Common.ps1"
. $common
$config = Get-DBGPTDeploymentConfig -ConfigPath $ConfigPath
$releaseVersion = Get-DBGPTReleaseVersion -ReleaseRoot $release
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$runtimeUserSid = $identity.User.Value
$runtimeUserName = $identity.Name
$desktop = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::DesktopDirectory
)
$localLogRoot = Join-Path $env:LOCALAPPDATA "HGTech\DB-GPT\Installer"
New-Item -ItemType Directory -Force -Path $localLogRoot | Out-Null
$logPath = Join-Path $localLogRoot (
    "setup-$((Get-Date).ToString('yyyyMMdd-HHmmss')).log"
)
$mutex = New-Object Threading.Mutex($false, "Local\HGTech-DBGPT-Offline-Setup")
$hasMutex = $false

function Write-SetupMessage {
    param([string]$Message)
    $line = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] $Message"
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function ConvertTo-SingleQuotedLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        throw "Another DB-GPT installation is already running"
    }
    Write-SetupMessage "Starting DB-GPT $releaseVersion installation."
    Write-SetupMessage "Install user: $runtimeUserName"
    Write-SetupMessage "Release media: $release"

    $systemScript = Join-Path $release "scripts\Install-DBGPTSystem.ps1"
    $command = (
        "& " + (ConvertTo-SingleQuotedLiteral $systemScript) +
        " -ReleaseRoot " + (ConvertTo-SingleQuotedLiteral $release) +
        " -ConfigPath " + (ConvertTo-SingleQuotedLiteral $ConfigPath) +
        " -RuntimeUserSid " + (ConvertTo-SingleQuotedLiteral $runtimeUserSid)
    )
    $encodedCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($command)
    )
    $processArguments = @{
        FilePath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        ArgumentList = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
            $encodedCommand
        )
        Wait = $true
        PassThru = $true
    }
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )) {
        $processArguments["Verb"] = "RunAs"
    }
    $systemProcess = Start-Process @processArguments

    if ($systemProcess.ExitCode -eq 3010) {
        $runOnce = (
            "`"$env:SystemRoot\System32\cmd.exe`" /c " +
            "`"`"$(Join-Path $release 'Install-DBGPT.cmd')`"`""
        )
        New-ItemProperty -Path (
            "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
        ) -Name "HGTechDBGPTOfflineSetup" -Value $runOnce `
            -PropertyType String -Force | Out-Null
        Write-SetupMessage "Windows must restart. Installation will resume after sign-in."
        exit 3010
    }
    if ($systemProcess.ExitCode -ne 0) {
        $resultPath = Join-Path $config.dataRoot "install\system-result.json"
        $detail = if (Test-Path -LiteralPath $resultPath -PathType Leaf) {
            (Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json).message
        }
        else {
            "System installation failed"
        }
        throw $detail
    }

    & (Join-Path $config.installRoot "scripts\Install-DBGPTDesktopShortcuts.ps1") `
        -InstallRoot $config.installRoot -DataRoot $config.dataRoot `
        -LlmModel $config.mainLlmModel `
        -FallbackLlmModel $config.fallbackLlmModel `
        -EmbeddingModel $config.embeddingModel `
        -ContextLength $config.contextLength -DesktopPath $desktop
    if ($LASTEXITCODE -ne 0) {
        throw "Desktop shortcut creation failed"
    }

    Remove-ItemProperty -Path (
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce"
    ) -Name "HGTechDBGPTOfflineSetup" -ErrorAction SilentlyContinue
    Write-SetupMessage "Installation completed. Use the desktop shortcut to start DB-GPT."
    exit 0
}
catch {
    Write-SetupMessage "FAILED: $($_.Exception.Message)"
    Write-SetupMessage "Log: $logPath"
    exit 1
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
