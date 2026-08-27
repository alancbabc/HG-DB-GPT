[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [ValidateSet("Apply", "Remove", "Status")]
    [string]$Action = "Status"
)

$ErrorActionPreference = "Stop"
$install = (Resolve-Path -LiteralPath $InstallRoot).Path
$ruleGroup = "HGTech DB-GPT Offline Runtime"
$specifications = @(
    @{
        Name = "HGTechDBGPTOffline-Python-BlockInternet"
        Program = Join-Path $install "python\python.exe"
    },
    @{
        Name = "HGTechDBGPTOffline-Ollama-BlockInternet"
        Program = Join-Path $install "ollama\ollama.exe"
    },
    @{
        Name = "HGTechDBGPTOffline-LlamaServer-BlockInternet"
        Program = Join-Path $install "ollama\lib\ollama\llama-server.exe"
    }
)

if ($Action -ne "Status") {
    if (-not $PSCmdlet.ShouldProcess(
        $install,
        "$Action DB-GPT process-level Internet blocking rules"
    )) {
        return
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )) {
        throw "Administrator PowerShell is required"
    }
}

if ($Action -eq "Apply") {
    foreach ($specification in $specifications) {
        if (-not (Test-Path -LiteralPath $specification.Program -PathType Leaf)) {
            throw "Required executable is missing: $($specification.Program)"
        }
        $existing = Get-NetFirewallRule -Name $specification.Name `
            -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            Remove-NetFirewallRule -Name $specification.Name
        }
        New-NetFirewallRule -Name $specification.Name `
            -DisplayName $specification.Name `
            -Group $ruleGroup `
            -Direction Outbound `
            -Program $specification.Program `
            -RemoteAddress "Internet" `
            -Action Block `
            -Profile Any `
            -Enabled True | Out-Null
    }
}
elseif ($Action -eq "Remove") {
    foreach ($specification in $specifications) {
        if (Get-NetFirewallRule -Name $specification.Name `
            -ErrorAction SilentlyContinue) {
            Remove-NetFirewallRule -Name $specification.Name
        }
    }
}

$results = foreach ($specification in $specifications) {
    $rule = Get-NetFirewallRule -Name $specification.Name `
        -ErrorAction SilentlyContinue
    if ($null -eq $rule) {
        [ordered]@{
            name = $specification.Name
            program = $specification.Program
            valid = $false
            reason = "missing"
        }
        continue
    }
    $application = Get-NetFirewallApplicationFilter `
        -AssociatedNetFirewallRule $rule
    $address = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
    $programMatches = $application.Program -eq $specification.Program
    $remoteAddresses = @($address.RemoteAddress)
    $valid = (
        $rule.Enabled -eq "True" -and
        $rule.Direction -eq "Outbound" -and
        $rule.Action -eq "Block" -and
        $programMatches -and
        $remoteAddresses -contains "Internet"
    )
    [ordered]@{
        name = $specification.Name
        program = $application.Program
        remoteAddress = $remoteAddresses
        enabled = $rule.Enabled.ToString()
        direction = $rule.Direction.ToString()
        action = $rule.Action.ToString()
        valid = $valid
        reason = if ($valid) { "ok" } else { "configuration mismatch" }
    }
}

$profiles = @(Get-NetFirewallProfile | ForEach-Object {
    [ordered]@{
        name = $_.Name.ToString()
        enabled = [bool]$_.Enabled
    }
})
$profilesEnabled = @($profiles | Where-Object { -not $_.enabled }).Count -eq 0
$success = @($results | Where-Object { -not $_.valid }).Count -eq 0 -and `
    $profilesEnabled
$report = [ordered]@{
    success = $success
    action = $Action
    ruleGroup = $ruleGroup
    rules = @($results)
    firewallProfiles = $profiles
}
$report | ConvertTo-Json -Depth 6
if ($Action -eq "Status" -and -not $success) {
    exit 1
}
exit 0
