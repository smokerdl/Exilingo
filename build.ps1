$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "=== Exilingo Windows build ===" -ForegroundColor Cyan
Write-Host "Project: $root"

Write-Host "`n[1/5] Checking Python..." -ForegroundColor Yellow
python --version

Write-Host "`n[2/5] Installing build dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "`n[3/5] Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}
if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
}

Write-Host "`n[4/5] Running PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller --clean --noconfirm Exilingo.spec

$bundleRoot = Join-Path $root "dist\Exilingo"

if (-not (Test-Path (Join-Path $bundleRoot "Exilingo.exe"))) {
    throw "PyInstaller did not produce dist\Exilingo\Exilingo.exe"
}

Write-Host "`n[5/5] Installing sanitized release config..." -ForegroundColor Yellow
Copy-Item "config.release.json" (Join-Path $bundleRoot "config.json") -Force

# Configuration is user data and must live beside Exilingo.exe, not inside
# PyInstaller's _internal directory.
$internalConfig = Join-Path $bundleRoot "_internal\config.json"
if (Test-Path $internalConfig) {
    Remove-Item $internalConfig -Force
}

$zipPath = Join-Path $root "dist\Exilingo-test.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $zipPath -Force

Write-Host "`n=== BUILD COMPLETE ===" -ForegroundColor Green
Write-Host "Executable: $bundleRoot\Exilingo.exe"
Write-Host "Archive:    $zipPath"
