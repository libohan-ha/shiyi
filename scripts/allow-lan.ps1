param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [string]$LanAddress
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator rights are required to add a firewall rule. Right-click allow-lan.cmd and choose Run as administrator.'
}
. (Join-Path $PSScriptRoot 'lan.ps1')
$lanInterface = Get-ShiyiLanInterface -Address $LanAddress
$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Run start-lan.cmd first to prepare the Python environment.' }
$python = & $launcher -c 'import sys; print(sys._base_executable)'
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw 'Unable to locate the Python runtime.' }
$ruleName = "Shiyi-LAN-TCP-$Port-$($lanInterface.InterfaceIndex)"
$parameters = @{
    Name = $ruleName
    DisplayName = "Shiyi LAN ($Port, $($lanInterface.InterfaceAlias))"
    Description = 'Allow Shiyi from the local subnet on the selected LAN adapter only.'
    Enabled = 'True'
    Direction = 'Inbound'
    Action = 'Allow'
    Profile = 'Any'
    Protocol = 'TCP'
    LocalPort = $Port
    LocalAddress = $lanInterface.Address
    RemoteAddress = 'LocalSubnet'
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
Write-Host "Only TCP $Port from the local subnet is allowed. Keep start-lan.cmd running."
Write-Host "To remove this rule: Remove-NetFirewallRule -Name '$ruleName'"
