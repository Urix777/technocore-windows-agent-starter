$ErrorActionPreference = "Stop"

$Root = "C:\Python\flop-agent"
Write-Host "Creating $Root ..."
New-Item -ItemType Directory -Force -Path $Root | Out-Null

$Source = Join-Path $PSScriptRoot "flop_agent.py"
Copy-Item $Source (Join-Path $Root "flop_agent.py") -Force

Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install "cryptography>=45,<48"

@"
@echo off
cd /d C:\Python\flop-agent
".venv\Scripts\python.exe" flop_agent.py %*
"@ | Set-Content -Encoding ASCII ".\flop.cmd"

@"
identity.pem
state.json
receipts.jsonl
.venv/
__pycache__/
"@ | Set-Content -Encoding ASCII ".\.gitignore"

Write-Host ""
Write-Host "Installed."
Write-Host "Next command:"
Write-Host "  C:\Python\flop-agent\flop.cmd init"
Write-Host ""
Write-Host "The private key will be generated locally on your PC, not in ChatGPT."
