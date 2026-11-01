# Pass-Through Launcher for HarnessAgents Virtual Office (Pure 7-bit ASCII)
param(
    [int]$Port = 8420
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonBin = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
Write-Host "Starting DevLabs / HarnessAgents v2.0 on http://127.0.0.1:$Port ..." -ForegroundColor Cyan
& $PythonBin -m harness_agents.cli serve --host 127.0.0.1 --port $Port
