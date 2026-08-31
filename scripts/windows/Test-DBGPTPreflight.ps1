[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot,
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [Parameter(Mandatory = $true)]
    [string]$ModelRoot,
    [int]$WebPort = 5670,
    [int]$OllamaPort = 11434
)

$ErrorActionPreference = "Stop"
$errors = [System.Collections.Generic.List[string]]::new()
$checks = [ordered]@{}
$details = [ordered]@{}

$release = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$checks["windows64Bit"] = [Environment]::Is64BitOperatingSystem -and `
    $env:OS -eq "Windows_NT"
if (-not $checks["windows64Bit"]) {
    $errors.Add("A 64-bit Windows operating system is required")
}

$destinationPaths = @($InstallRoot, $DataRoot, $ModelRoot)
foreach ($path in $destinationPaths) {
    if (-not [IO.Path]::IsPathRooted($path) -or $path.StartsWith("\\")) {
        $errors.Add("Destination must be an absolute local path: $path")
        continue
    }
    try {
        $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($path))
        if ($drive.DriveType -ne [IO.DriveType]::Fixed) {
            $errors.Add("Destination must use a fixed local disk: $path")
        }
    }
    catch {
        $errors.Add("Destination drive is unavailable: $path")
    }
}

$releasePrefix = $release.TrimEnd("\") + "\"
foreach ($path in $destinationPaths) {
    $fullPath = [IO.Path]::GetFullPath($path).TrimEnd("\") + "\"
    if ($fullPath.StartsWith($releasePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        $errors.Add("Runtime destination must not be inside the release media: $path")
    }
}

$modelBytes = (Get-ChildItem -LiteralPath (Join-Path $release "models") `
    -Recurse -File | Measure-Object -Property Length -Sum).Sum
$sameReleaseInstalled = $false
$installedManifestPath = Join-Path $InstallRoot "release-manifest.json"
if (Test-Path -LiteralPath $installedManifestPath -PathType Leaf) {
    try {
        $sourceVersion = (
            Get-Content -LiteralPath (Join-Path $release "release-manifest.json") `
                -Raw | ConvertFrom-Json
        ).releaseVersion
        $installedVersion = (
            Get-Content -LiteralPath $installedManifestPath -Raw | ConvertFrom-Json
        ).releaseVersion
        $sameReleaseInstalled = $sourceVersion -eq $installedVersion
    }
    catch {
        $sameReleaseInstalled = $false
    }
}
$modelStorePresent = (Test-Path -LiteralPath (Join-Path $ModelRoot "manifests") `
    -PathType Container) -and (Test-Path -LiteralPath (
        Join-Path $ModelRoot "blobs"
    ) -PathType Container)
$installRequiredBytes = if ($sameReleaseInstalled) { 1GB } else { 10GB }
$modelRequiredBytes = if ($modelStorePresent) {
    1GB
}
else {
    [int64]$modelBytes + 2GB
}
$requiredByDrive = @{}
foreach ($requirement in @(
    @{ Path = $InstallRoot; Bytes = $installRequiredBytes },
    @{ Path = $DataRoot; Bytes = 5GB },
    @{ Path = $ModelRoot; Bytes = $modelRequiredBytes }
)) {
    $root = [IO.Path]::GetPathRoot($requirement.Path).ToUpperInvariant()
    if (-not $requiredByDrive.ContainsKey($root)) {
        $requiredByDrive[$root] = [int64]0
    }
    $requiredByDrive[$root] += [int64]$requirement.Bytes
}
$space = @()
foreach ($root in $requiredByDrive.Keys) {
    try {
        $drive = [IO.DriveInfo]::new($root)
        $enough = $drive.AvailableFreeSpace -ge $requiredByDrive[$root]
        $space += [pscustomobject]@{
            drive = $root
            availableBytes = $drive.AvailableFreeSpace
            requiredBytes = $requiredByDrive[$root]
            enough = $enough
        }
        if (-not $enough) {
            $errors.Add("Insufficient free space on $root")
        }
    }
    catch {
        $errors.Add("Unable to inspect free space on $root")
    }
}
$details["diskSpace"] = $space
$checks["diskSpaceSufficient"] = -not ($space | Where-Object { -not $_.enough })

$ollamaServiceExists = $null -ne (
    Get-Service -Name "HGTechOllama" -ErrorAction SilentlyContinue
)
$dbgptPidPath = Join-Path $DataRoot "run\dbgpt.pid"
foreach ($portCheck in @(
    @{ Name = "webPortAvailable"; Port = $WebPort; Allow = (Test-Path -LiteralPath $dbgptPidPath) },
    @{ Name = "ollamaPortAvailable"; Port = $OllamaPort; Allow = $ollamaServiceExists }
)) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $portCheck.Port `
        -ErrorAction SilentlyContinue)
    $available = $listeners.Count -eq 0 -or $portCheck.Allow
    $checks[$portCheck.Name] = $available
    if (-not $available) {
        $errors.Add("TCP port $($portCheck.Port) is already in use")
    }
}

$report = [ordered]@{
    success = $errors.Count -eq 0
    checkedAt = (Get-Date).ToUniversalTime().ToString("o")
    checks = $checks
    details = $details
    errors = $errors
}
$report | ConvertTo-Json -Depth 8
if ($errors.Count -ne 0) {
    exit 1
}
exit 0
