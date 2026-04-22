param(
  [string]$ProjectRoot = "C:\Users\Administrator\Documents\Playground\ai-music-tool"
)

$ErrorActionPreference = "Stop"

$patchPath = Join-Path $ProjectRoot "tools\py314_tempfile_fix"
$tempBase = Join-Path $ProjectRoot ".tmp_python"
New-Item -ItemType Directory -Force -Path $tempBase | Out-Null

$env:PYTHONPATH = $patchPath
$env:PY_TEMP_BASE = $tempBase

Write-Host "Using tempfile patch: $env:PYTHONPATH"
Write-Host "Temporary base dir   : $env:PY_TEMP_BASE"

Set-Location $ProjectRoot

# Use `python -m pip` rather than `pip` so the patch is guaranteed to apply.
python -m pip install --prefer-binary --only-binary=pydantic-core,jiter -r ".\backend\requirements.txt"
