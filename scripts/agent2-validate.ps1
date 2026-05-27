$ErrorActionPreference = "Stop"

Set-Location -LiteralPath "D:\AgentesGuille"
python build_landings.py validate
