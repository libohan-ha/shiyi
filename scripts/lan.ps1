function Get-ShiyiLanInterface {
    param([string]$Address)

    $configurations = @(Get-NetIPConfiguration -ErrorAction Stop)
    if ($Address) {
        $parsed = $null
        if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed) -or
            $parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
            [System.Net.IPAddress]::IsLoopback($parsed) -or $parsed.ToString().StartsWith('169.254.')) {
            throw 'LanAddress must be a LAN IPv4 address assigned to this computer.'
        }
        $Address = $parsed.ToString()
        $configuration = $configurations | Where-Object { @($_.IPv4Address | ForEach-Object { $_.IPAddress }) -contains $Address } | Select-Object -First 1
    } else {
        $physicalIndices = @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty InterfaceIndex)
        $configuration = $configurations | Where-Object {
            $_.InterfaceIndex -in $physicalIndices -and $_.IPv4DefaultGateway -and
            @($_.IPv4Address | Where-Object { $_.IPAddress -notlike '169.254.*' }).Count -gt 0
        } | Sort-Object { $_.NetIPv4Interface.InterfaceMetric } | Select-Object -First 1
        if ($configuration) {
            $Address = $configuration.IPv4Address | Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1 -ExpandProperty IPAddress
        }
    }
    if (-not $configuration) {
        throw 'No connected LAN adapter found. Connect to Wi-Fi/Ethernet or pass -LanAddress with a local IPv4 address.'
    }
    [PSCustomObject]@{ Address = $Address; InterfaceAlias = $configuration.InterfaceAlias; InterfaceIndex = $configuration.InterfaceIndex }
}
