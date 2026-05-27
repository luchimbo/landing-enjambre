$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python .\swarm.py auto-listen --channels all --searches 3 --per-search 2
python .\swarm.py auto-distribution --channels all --limit 6 --per-channel 1
