$ErrorActionPreference = "Stop"

$Root = "C:\Python\flop-agent"
Write-Host "Updating/installing Technocore starter in $Root ..."
New-Item -ItemType Directory -Force -Path $Root | Out-Null

# Preserve identity.pem/state/receipts if this is an upgrade.
$Source = Join-Path $PSScriptRoot "flop_agent.py"
Copy-Item $Source (Join-Path $Root "flop_agent.py") -Force

Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install "cryptography>=45,<51"

@"
@echo off
cd /d C:\Python\flop-agent
".venv\Scripts\python.exe" flop_agent.py %*
"@ | Set-Content -Encoding ASCII ".\flop.cmd"

@"
identity.pem
state.json
receipts.jsonl
technocore-evidence.json
.venv/
__pycache__/
*.pyc
.env
secrets.json
"@ | Set-Content -Encoding ASCII ".\.gitignore"

Write-Host ""
Write-Host "Installed/updated without replacing identity.pem."
Write-Host "Recommended check:"
Write-Host "  C:\Python\flop-agent\flop.cmd doctor"
Write-Host ""
