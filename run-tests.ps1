$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m unittest -v test_flop_agent.py
