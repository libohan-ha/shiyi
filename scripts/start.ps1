param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$SkipBuild,
    [switch]$Lan,
    [string]$LanAddress,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$runtimeRoot = Join-Path $projectRoot '.local'
$listenAddress = '127.0.0.1'
$lanInterface = $null
if ($Lan -or $LanAddress) {
    . (Join-Path $PSScriptRoot 'lan.ps1')
    $lanInterface = Get-ShiyiLanInterface -Address $LanAddress
    $listenAddress = '0.0.0.0'
}

function Test-ShiyiServer {
    param([string]$BaseUrl)

    try {
        $documents = @{}
        foreach ($path in @('/api/health', '/api/openapi.json')) {
            $request = [System.Net.HttpWebRequest]::Create($BaseUrl + $path)
            $request.Proxy = $null
            $request.Timeout = 3000
            $request.ReadWriteTimeout = 3000
            $request.AllowAutoRedirect = $false
            $response = $request.GetResponse()
            try {
                if ([int]$response.StatusCode -ne 200) { return $false }
                $reader = [System.IO.StreamReader]::new($response.GetResponseStream())
                try { $documents[$path] = $reader.ReadToEnd() | ConvertFrom-Json }
                finally { $reader.Dispose() }
            } finally { $response.Dispose() }
        }
        # Keep this script compatible with Windows PowerShell's default file encoding.
        $expectedTitle = [regex]::Unescape('\u62fe\u5fc6 API')
        return ($documents['/api/health'].status -eq 'ok' -and
            $documents['/api/openapi.json'].info.title -ceq $expectedTitle -and
            '/api/v1/reviews/due' -in $documents['/api/openapi.json'].paths.PSObject.Properties.Name)
    } catch { return $false }
}

$localUrl = "http://127.0.0.1:$Port"
$requestedUrl = if ($lanInterface) { "http://$($lanInterface.Address):$Port" } else { $localUrl }
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    if (Test-ShiyiServer -BaseUrl $requestedUrl) {
        Write-Host "`nShiyi is already running. Opening the existing service."
        Write-Host "Local: $localUrl"
        if ($lanInterface) { Write-Host "LAN:   $requestedUrl ($($lanInterface.InterfaceAlias))" }
        Write-Host 'Keep the original server running. To rebuild or change its settings, stop it with Ctrl+C first.'
        if (-not $NoBrowser) {
            try { Start-Process -FilePath $requestedUrl | Out-Null }
            catch { Write-Host "Open this address in your browser: $requestedUrl" }
        }
        return
    }
    if ($lanInterface -and (Test-ShiyiServer -BaseUrl $localUrl)) {
        throw "Shiyi is running at $localUrl, but cannot be reached at $requestedUrl. Stop the original server with Ctrl+C, then run start-lan.cmd again."
    }
    $processIds = ($listeners.OwningProcess | Sort-Object -Unique) -join ', '
    throw "Port $Port is occupied by another service or an unresponsive Shiyi instance (PID: $processIds). Stop that service or choose another port with -Port."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' }

Push-Location $backendRoot
try {
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    & uv run --frozen alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
} finally { Pop-Location }

if (-not $SkipBuild) {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 or later first.' }
    Push-Location $frontendRoot
    try {
        $lockHash = (Get-FileHash -LiteralPath 'package-lock.json' -Algorithm SHA256).Hash
        $stampPath = Join-Path $runtimeRoot 'frontend-lock.sha256'
        $installedHash = if (Test-Path -LiteralPath $stampPath) { (Get-Content -LiteralPath $stampPath -Raw).Trim() } else { '' }
        if (-not (Test-Path -LiteralPath 'node_modules') -or $installedHash -ne $lockHash) {
            & npm.cmd ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
            New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
            Set-Content -LiteralPath $stampPath -Value $lockHash -Encoding ASCII
        }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'dist/index.html'))) { throw 'Frontend build is missing. Run again without -SkipBuild.' }

$envPath = Join-Path $backendRoot '.env'
$hasConfiguredUrl = (Test-Path -LiteralPath $envPath) -and (Select-String -LiteralPath $envPath -Pattern '^\s*SHIYI_PUBLIC_URL\s*=' -Quiet)
$previousEnvironment = @{}
foreach ($name in @('SHIYI_PUBLIC_URL', 'SHIYI_TRUSTED_HOSTS', 'SHIYI_ALLOWED_ORIGINS')) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

Push-Location $backendRoot
try {
    $python = Join-Path $backendRoot '.venv/Scripts/python.exe'
    $configurationJson = & $python -c 'import json; from app.config import settings; print(json.dumps(dict(trusted_hosts=settings.trusted_hosts, allowed_origins=settings.allowed_origins, secure_cookies=settings.secure_cookies)))'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read application settings.' }
    $configuration = $configurationJson | ConvertFrom-Json
    if ($lanInterface -and $configuration.secure_cookies) {
        throw 'HTTP LAN mode requires SHIYI_SECURE_COOKIES=false. Use your HTTPS deployment for secure cookies.'
    }
    $hosts = @($configuration.trusted_hosts -split ',') + @('localhost', '127.0.0.1')
    $origins = @($configuration.allowed_origins -split ',')
    if (-not $configuration.secure_cookies) {
        $origins += @("http://127.0.0.1:$Port", "http://localhost:$Port")
    }
    if ($lanInterface) {
        $lanUrl = "http://$($lanInterface.Address):$Port"
        $hosts += $lanInterface.Address
        $origins += $lanUrl
    }
    $env:SHIYI_TRUSTED_HOSTS = ($hosts | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique) -join ','
    $env:SHIYI_ALLOWED_ORIGINS = ($origins | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -Unique) -join ','
    if (-not $env:SHIYI_PUBLIC_URL -and -not $hasConfiguredUrl) {
        $env:SHIYI_PUBLIC_URL = if ($lanInterface) { $lanUrl } else { "http://127.0.0.1:$Port" }
    }
    Write-Host "`nLocal: http://127.0.0.1:$Port"
    if ($lanInterface) {
        Write-Host "LAN:   $lanUrl ($($lanInterface.InterfaceAlias))"
        Write-Host "API:   $lanUrl/api/docs"
        Write-Host 'Windows firewall setup: right-click allow-lan.cmd and choose Run as administrator (once).'
    } else { Write-Host "API:   http://127.0.0.1:$Port/api/docs" }
    Write-Host "Press Ctrl+C to stop. Your data stays in backend/data.`n"
    & $python -m uvicorn app.main:app --host $listenAddress --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'The server stopped with an error.' }
} finally {
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
    Pop-Location
}
