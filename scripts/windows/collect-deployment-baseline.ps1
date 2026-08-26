[CmdletBinding()]
param(
    [string]$PythonPath = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$warnings = [System.Collections.Generic.List[string]]::new()

function Get-CommandOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        return $null
    }

    try {
        return (& $CommandName @Arguments 2>$null | Out-String).Trim()
    }
    catch {
        $warnings.Add("Unable to collect output from ${CommandName}: $($_.Exception.Message)")
        return $null
    }
}

$cpu = $null
$memoryBytes = $null
try {
    $computerSystem = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $processor = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
    $cpu = [ordered]@{
        name = $processor.Name
        cores = $processor.NumberOfCores
        logicalProcessors = $processor.NumberOfLogicalProcessors
    }
    $memoryBytes = [int64]$computerSystem.TotalPhysicalMemory
}
catch {
    $warnings.Add("CIM hardware details unavailable: $($_.Exception.Message)")
}

$python = $null
if (Test-Path -LiteralPath $PythonPath -PathType Leaf) {
    try {
        $pythonJson = & $PythonPath -c "import json,platform,sqlite3,sys; print(json.dumps({'version':sys.version.split()[0],'architecture':platform.machine(),'sqliteVersion':sqlite3.sqlite_version}))"
        $python = $pythonJson | ConvertFrom-Json
    }
    catch {
        $warnings.Add("Python baseline unavailable: $($_.Exception.Message)")
    }
}
else {
    $warnings.Add("Python executable not found at $PythonPath")
}

$gpuOutput = Get-CommandOutput -CommandName "nvidia-smi" -Arguments @(
    "--query-gpu=name,memory.total,driver_version",
    "--format=csv,noheader"
)
$gitRevision = Get-CommandOutput -CommandName "git" -Arguments @("rev-parse", "HEAD")
$gitBranch = Get-CommandOutput -CommandName "git" -Arguments @("branch", "--show-current")

$baseline = [ordered]@{
    collectedAt = (Get-Date).ToUniversalTime().ToString("o")
    operatingSystem = [ordered]@{
        description = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
        architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        version = [Environment]::OSVersion.Version.ToString()
    }
    powershellVersion = $PSVersionTable.PSVersion.ToString()
    cpu = $cpu
    physicalMemoryBytes = $memoryBytes
    gpu = $gpuOutput
    python = $python
    git = [ordered]@{
        branch = $gitBranch
        revision = $gitRevision
    }
    warnings = $warnings
}

$baseline | ConvertTo-Json -Depth 6
