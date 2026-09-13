$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot 'backend')
try {
    & uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & uv run --frozen ruff check app tests migrations ../scripts
    if ($LASTEXITCODE -ne 0) { throw 'Python lint failed.' }
    & uv run --frozen pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
} finally { Pop-Location }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    & npm.cmd run test:e2e
    if ($LASTEXITCODE -ne 0) { throw 'Browser tests failed. See frontend/playwright-report.' }
} finally { Pop-Location }
Write-Host 'All checks passed.'
