param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [string]$LanAddress,
    [switch]$Tailscale
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator rights are required to add a firewall rule. Right-click allow-lan.cmd and choose Run as administrator.'
}
. (Join-Path $PSScriptRoot 'lan.ps1')
if ($Tailscale) {
    . (Join-Path $PSScriptRoot 'tailscale.ps1')
    $tailscaleAddress = (Get-ShiyiTailscaleIdentity).Addresses[0]
    $tailscaleIp = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $tailscaleAddress -ErrorAction Stop | Select-Object -First 1
    $lanInterface = [PSCustomObject]@{ Address = $tailscaleAddress; InterfaceAlias = $tailscaleIp.InterfaceAlias; InterfaceIndex = $tailscaleIp.InterfaceIndex }
    # Tailscale's CGNAT range: only devices in your tailnet can reach this address.
    $remoteAddress = '100.64.0.0/10'
} else {
    $lanInterface = Get-ShiyiLanInterface -Address $LanAddress
    $remoteAddress = 'LocalSubnet'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Run start-lan.cmd first to prepare the Python environment.' }
$python = & $launcher -c 'import sys; print(sys._base_executable)'
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw 'Unable to locate the Python runtime.' }
$rulePrefix = if ($Tailscale) { 'Shiyi-Tailscale' } else { 'Shiyi-LAN' }
$ruleName = "$rulePrefix-TCP-$Port-$($lanInterface.InterfaceIndex)"
$parameters = @{
    Name = $ruleName
    DisplayName = "$($rulePrefix.Replace('-', ' ')) ($Port, $($lanInterface.InterfaceAlias))"
    Description = 'Allow Shiyi only from the selected adapter (local subnet, or tailnet devices for Tailscale).'
    Enabled = 'True'
    Direction = 'Inbound'
    Action = 'Allow'
    Profile = 'Any'
    Protocol = 'TCP'
    LocalPort = $Port
    LocalAddress = $lanInterface.Address
    RemoteAddress = $remoteAddress
    InterfaceAlias = $lanInterface.InterfaceAlias
    Program = $python
    EdgeTraversalPolicy = 'Block'
}
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    $parameters.NewDisplayName = $parameters.DisplayName
    $parameters.Remove('DisplayName')
    Set-NetFirewallRule @parameters | Out-Null
} else {
    New-NetFirewallRule @parameters | Out-Null
}
Write-Host "Ready: http://$($lanInterface.Address):$Port"
if ($Tailscale) { Write-Host "Only TCP $Port from your tailnet is allowed. Keep start-tailscale.cmd running." }
else { Write-Host "Only TCP $Port from the local subnet is allowed. Keep start-lan.cmd running." }
Write-Host "To remove this rule: Remove-NetFirewallRule -Name '$ruleName'"
