function Get-ShiyiTailscaleIdentity {
    # Reads this computer's tailnet IPv4 address and MagicDNS names from the Tailscale CLI.
    $command = Get-Command tailscale -ErrorAction SilentlyContinue
    $cli = if ($command) { $command.Source } else { Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe' }
    if (-not (Test-Path -LiteralPath $cli)) {
        throw 'Tailscale CLI not found. Install Tailscale, or pass -AllowHost with your tailnet address/name instead.'
    }
    $json = & $cli status --json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) { throw 'Tailscale is not running. Open Tailscale and connect, then try again.' }
    $status = ($json -join "`n") | ConvertFrom-Json
    $state = $status.PSObject.Properties['BackendState']
    if ($state -and $state.Value -ne 'Running') { throw "Tailscale is not connected (state: $($state.Value)). Connect it, then try again." }
    $self = $status.PSObject.Properties['Self']
    if (-not $self -or -not $self.Value) { throw 'Unable to read this computer from tailscale status.' }
    $self = $self.Value

    $addresses = @()
    $ips = $self.PSObject.Properties['TailscaleIPs']
    if ($ips -and $ips.Value) { $addresses = @($ips.Value | Where-Object { $_ -match '^\d{1,3}(\.\d{1,3}){3}$' }) }
    if ($addresses.Count -eq 0) { throw 'This computer has no Tailscale IPv4 address yet.' }

    $names = @()
    $dns = $self.PSObject.Properties['DNSName']
    if ($dns -and $dns.Value) {
        $full = $dns.Value.TrimEnd('.').ToLowerInvariant()
        if ($full) { $names += $full; $names += $full.Split('.')[0] }
    }
    [PSCustomObject]@{ Addresses = $addresses; Names = @($names | Select-Object -Unique) }
}

function Test-ShiyiHostName {
    param([string]$Name)
    $parsed = $null
    if ([System.Net.IPAddress]::TryParse($Name, [ref]$parsed)) { return $true }
    return $Name -match '^(\*\.)?[a-z0-9]([a-z0-9-]{0,62})(\.[a-z0-9]([a-z0-9-]{0,62}))*$'
}
