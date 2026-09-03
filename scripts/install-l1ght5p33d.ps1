param([switch]$Developer)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$packageRoot = Join-Path $repositoryRoot 'packages\l1ght5p33d'
$env:PYTHONUTF8 = '1'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -m venv (Join-Path $packageRoot '.bootstrap')
} else {
    $pythonVersion = & python -c 'import sys; print(str(sys.version_info.major)+"."+str(sys.version_info.minor))'
    if ($pythonVersion -ne '3.12') { throw 'Install Python 3.12, then rerun this installer.' }
    & python -m venv (Join-Path $packageRoot '.bootstrap')
}
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment creation failed.' }
$bootstrapPython = Join-Path $packageRoot '.bootstrap\Scripts\python.exe'
& $bootstrapPython -m pip install --disable-pip-version-check uv==0.12.9
if ($LASTEXITCODE -ne 0) { throw 'uv installation failed.' }
$uvExecutable = Join-Path $packageRoot '.bootstrap\Scripts\uv.exe'
if ($Developer) { & $uvExecutable sync --project $packageRoot --frozen --extra dev }
else { & $uvExecutable sync --project $packageRoot --frozen }
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
$runnerPython = Join-Path $packageRoot '.venv\Scripts\python.exe'
& $runnerPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
& $runnerPython -X utf8 -m l1ght5p33d --version
if ($LASTEXITCODE -ne 0) { throw 'L1ght5p33d import check failed.' }
Write-Host 'Installed. Try a reviewed workflow with local approval:'
Write-Host "& '$runnerPython' -X utf8 -m l1ght5p33d try"
