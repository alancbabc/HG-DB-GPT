[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$ModelRoot,
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$release = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$releaseManifestPath = Join-Path $release "release-manifest.json"
$releaseManifest = Get-Content -LiteralPath $releaseManifestPath -Raw | `
    ConvertFrom-Json
$installMarkerPath = Join-Path $InstallRoot ".dbgpt-offline-installing.json"
& (Join-Path $release "scripts\Test-OfflineRelease.ps1") -ReleaseRoot $release
if ($LASTEXITCODE -ne 0) {
    throw "Offline release verification failed"
}
if (Test-Path -LiteralPath $InstallRoot) {
    if (-not $Resume) {
        throw "InstallRoot already exists; use upgrade/rollback workflow: $InstallRoot"
    }
    $installedManifestPath = Join-Path $InstallRoot "release-manifest.json"
    $resumeVersion = $null
    if (Test-Path -LiteralPath $installedManifestPath -PathType Leaf) {
        $resumeVersion = (
            Get-Content -LiteralPath $installedManifestPath -Raw | ConvertFrom-Json
        ).releaseVersion
        if ($resumeVersion -ne $releaseManifest.releaseVersion) {
            throw (
                "Refusing to overwrite a completed installation from release " +
                "$resumeVersion`: $InstallRoot"
            )
        }
    }
    elseif (Test-Path -LiteralPath $installMarkerPath -PathType Leaf) {
        $resumeVersion = (
            Get-Content -LiteralPath $installMarkerPath -Raw | ConvertFrom-Json
        ).releaseVersion
        if ([string]::IsNullOrWhiteSpace([string]$resumeVersion)) {
            throw "The incomplete installation marker is invalid: $installMarkerPath"
        }
        Write-Output (
            "Resuming incomplete release $resumeVersion as " +
            "$($releaseManifest.releaseVersion)"
        )
    }
    else {
        throw (
            "Refusing to overwrite an unrecognized existing directory: $InstallRoot"
        )
    }
}
if (-not $PSCmdlet.ShouldProcess($InstallRoot, "Install DB-GPT offline release")) {
    return
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator PowerShell is required"
}

$runtimeLock = Get-Content -Raw -LiteralPath (
    Join-Path $release "scripts\runtime-media.lock.json"
) | ConvertFrom-Json
$vcArtifact = $runtimeLock.artifacts | Where-Object { $_.id -eq "vcRedist" }
if ($null -eq $vcArtifact) {
    throw "VC++ runtime version is missing from runtime-media.lock.json"
}
$requiredVcVersion = [version]$vcArtifact.version
$vcRegistryPath = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$installedVc = Get-ItemProperty -LiteralPath $vcRegistryPath `
    -ErrorAction SilentlyContinue
$installedVcVersion = $null
if ($null -ne $installedVc -and $installedVc.Installed -eq 1) {
    try {
        $installedVcVersion = [version]($installedVc.Version.TrimStart("v"))
    }
    catch {
        $installedVcVersion = $null
    }
}
if ($null -eq $installedVcVersion -or $installedVcVersion -lt $requiredVcVersion) {
    $vcRedist = Join-Path $release "runtime\vc-redist.x64.exe"
    $vcProcess = Start-Process -FilePath $vcRedist `
        -ArgumentList @("/install", "/quiet", "/norestart") `
        -WindowStyle Hidden -PassThru
    $vcProcess.WaitForExit()
    if ($vcProcess.ExitCode -eq 3010) {
        throw "Visual C++ runtime installed; Windows restart is required before rerunning this installer"
    }
    if ($vcProcess.ExitCode -notin @(0, 1638)) {
        throw "Visual C++ Redistributable failed with exit code $($vcProcess.ExitCode)"
    }
    $installedVc = Get-ItemProperty -LiteralPath $vcRegistryPath `
        -ErrorAction SilentlyContinue
    if ($null -eq $installedVc -or $installedVc.Installed -ne 1) {
        throw "Visual C++ runtime installation was not registered"
    }
    $installedVcVersion = [version]($installedVc.Version.TrimStart("v"))
    if ($installedVcVersion -lt $requiredVcVersion) {
        throw "Installed Visual C++ runtime is older than $requiredVcVersion"
    }
}
else {
    Write-Output "Visual C++ runtime $installedVcVersion already satisfies $requiredVcVersion"
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
[ordered]@{
    releaseVersion = $releaseManifest.releaseVersion
    releaseRoot = $release
    updatedAt = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $installMarkerPath -Encoding UTF8
New-Item -ItemType Directory -Force -Path $DataRoot, $ModelRoot | Out-Null
$pythonRoot = Join-Path $InstallRoot "python"
$pythonInstaller = Join-Path $release "runtime\python-installer.exe"
$pythonInstallLog = Join-Path $DataRoot "install\python-installer.log"
New-Item -ItemType Directory -Force -Path (Split-Path $pythonInstallLog) | Out-Null
$legacyBrokenRoot = "C:\Program"
$legacyBrokenPython = Join-Path $legacyBrokenRoot "python.exe"
if ($resumeVersion -eq "0.8.1-dev-deploy-20260831-stage21.3" -and `
    -not (Test-Path -LiteralPath (Join-Path $pythonRoot "python.exe") `
        -PathType Leaf) -and `
    (Test-Path -LiteralPath $legacyBrokenPython -PathType Leaf)) {
    $legacyVersionMatches = $false
    & $legacyBrokenPython -c (
        "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 11, 9) else 1)"
    )
    $legacyVersionMatches = $LASTEXITCODE -eq 0
    $pythonRegistryKey = Get-Item -LiteralPath (
        "HKLM:\SOFTWARE\Python\PythonCore\3.11\InstallPath"
    ) -ErrorAction SilentlyContinue
    $registeredPythonRoot = if ($null -ne $pythonRegistryKey) {
        [string]$pythonRegistryKey.GetValue("")
    }
    else {
        ""
    }
    if ($legacyVersionMatches -and `
        [IO.Path]::GetFullPath($registeredPythonRoot).TrimEnd("\") -eq `
        $legacyBrokenRoot) {
        Write-Output "Removing the Stage 21.3 Python installation from C:\Program."
        $cleanupProcess = Start-Process -FilePath $pythonInstaller `
            -ArgumentList @("/uninstall", "/quiet") `
            -WindowStyle Hidden -PassThru
        $cleanupProcess.WaitForExit()
        if ($cleanupProcess.ExitCode -eq 3010) {
            throw "Python cleanup completed; Windows restart is required before rerunning"
        }
        if ($cleanupProcess.ExitCode -ne 0 -or `
            (Test-Path -LiteralPath $legacyBrokenPython -PathType Leaf)) {
            throw "Unable to remove the Stage 21.3 Python installation from C:\Program"
        }
    }
}
$arguments = @(
    "/quiet",
    "/log",
    "`"$pythonInstallLog`"",
    "InstallAllUsers=1",
    "TargetDir=`"$pythonRoot`"",
    "Include_pip=1",
    "Include_test=0",
    "Include_launcher=0",
    "AssociateFiles=0",
    "Shortcuts=0",
    "PrependPath=0"
)
$python = Join-Path $pythonRoot "python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $process = Start-Process -FilePath $pythonInstaller -ArgumentList $arguments `
        -WindowStyle Hidden -PassThru
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Python installer failed with exit code $($process.ExitCode)"
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw (
            "Python installer did not create the expected executable: $python. " +
            "See $pythonInstallLog"
        )
    }
}
else {
    & $python -c (
        "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 11, 9) else 1)"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Existing installation does not contain Python 3.11.9: $python"
    }
}

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

foreach ($directoryName in @(
    "ollama", "tools", "scripts", "metadata-template", "tiktoken-cache"
)) {
    $sourceDirectory = Join-Path $release $directoryName
    $destinationDirectory = Join-Path $InstallRoot $directoryName
    New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
    Get-ChildItem -LiteralPath $sourceDirectory -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destinationDirectory `
            -Recurse -Force
    }
}
Get-ChildItem -LiteralPath (Join-Path $release "models") -Force | `
    ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $ModelRoot -Recurse -Force
    }
& $python (Join-Path $InstallRoot "scripts\ollama_model_store.py") $ModelRoot
if ($LASTEXITCODE -ne 0) {
    throw "Installed Ollama model store validation failed"
}
New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot "config") | `
    Out-Null
$installedConfig = Join-Path $InstallRoot `
    "config\dbgpt-windows-offline-ollama.toml"
if (-not (Test-Path -LiteralPath $installedConfig -PathType Leaf)) {
    Copy-Item -LiteralPath (
        Join-Path $release "config\dbgpt-windows-offline-ollama.example.toml"
    ) -Destination $installedConfig
}
Copy-Item -LiteralPath (Join-Path $release "release-manifest.json") `
    -Destination (Join-Path $InstallRoot "release-manifest.json") -Force
Remove-Item -LiteralPath $installMarkerPath -Force -ErrorAction SilentlyContinue

Write-Output "Offline files installed. Register the Ollama service and DB-GPT desktop shortcuts next."
