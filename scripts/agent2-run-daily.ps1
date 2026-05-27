$ErrorActionPreference = "Stop"

Set-Location -LiteralPath "D:\AgentesGuille"
python build_landings.py run --limit 5 --max-seconds 1200 --base-url https://blog.pcmidicenter.com
