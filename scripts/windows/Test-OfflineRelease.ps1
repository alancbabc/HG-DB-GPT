[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseRoot
)

$ErrorActionPreference = "Stop"

function Get-Sha256Hex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        $bytes = $algorithm.ComputeHash($stream)
        return ([BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

$root = (Resolve-Path -LiteralPath $ReleaseRoot).Path
$manifestPath = Join-Path $root "release-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Missing release-manifest.json in $root"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schemaVersion -notin @(1, 2)) {
    throw "Unsupported release manifest schema: $($manifest.schemaVersion)"
}
$errors = [System.Collections.Generic.List[string]]::new()
foreach ($entry in $manifest.files) {
    $path = Join-Path $root ($entry.path -replace "/", "\")
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $errors.Add("Missing file: $($entry.path)")
        continue
    }
    $item = Get-Item -LiteralPath $path
    if ($item.Length -ne $entry.size) {
        $errors.Add("Size mismatch: $($entry.path)")
        continue
    }
    if ($null -ne $entry.sha256 -and -not [string]::IsNullOrWhiteSpace($entry.sha256)) {
        $hash = Get-Sha256Hex -Path $path
        if ($hash -ne $entry.sha256) {
            $errors.Add("SHA-256 mismatch: $($entry.path)")
        }
    }
}

$report = [ordered]@{
    success = $errors.Count -eq 0
    releaseVersion = $manifest.releaseVersion
    fileCount = $manifest.files.Count
    errors = $errors
}
$report | ConvertTo-Json -Depth 4
if ($errors.Count -ne 0) {
    exit 1
}
