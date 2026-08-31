function Get-DBGPTDeploymentConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigPath
    )

    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Deployment configuration is missing: $ConfigPath"
    }
    try {
        $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Deployment configuration is invalid JSON: $ConfigPath"
    }

    foreach ($name in @("installRoot", "dataRoot", "modelRoot")) {
        $value = [string]$config.$name
        if ([string]::IsNullOrWhiteSpace($value) -or `
            -not [IO.Path]::IsPathRooted($value) -or `
            $value.StartsWith("\\")) {
            throw "$name must be an absolute local Windows path"
        }
        $config.$name = [IO.Path]::GetFullPath(
            [Environment]::ExpandEnvironmentVariables($value)
        ).TrimEnd("\")
    }
    foreach ($portName in @("webPort", "ollamaPort")) {
        $port = [int]$config.$portName
        if ($port -lt 1 -or $port -gt 65535) {
            throw "$portName must be between 1 and 65535"
        }
        $config.$portName = $port
    }
    $contextLength = [int]$config.contextLength
    if ($contextLength -lt 2048 -or $contextLength -gt 131072) {
        throw "contextLength must be between 2048 and 131072"
    }
    $config.contextLength = $contextLength
    foreach ($name in @(
        "mainLlmModel", "fallbackLlmModel", "embeddingModel"
    )) {
        if ([string]::IsNullOrWhiteSpace([string]$config.$name)) {
            throw "$name must not be empty"
        }
    }
    return $config
}

function Get-DBGPTReleaseVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReleaseRoot
    )

    $manifestPath = Join-Path $ReleaseRoot "release-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Release manifest is missing: $manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$manifest.releaseVersion)) {
        throw "Release manifest has no releaseVersion"
    }
    return [string]$manifest.releaseVersion
}
