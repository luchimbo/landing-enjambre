<#
.SYNOPSIS
    Pipeline diario: nurture + conversion + distribution + search-threads + publish.
    Programado via Windows Task Scheduler:
      - Lunes 13:30 ART (despues del weekly)
      - Mar-Vie 10:30 ART
#>
param(
    [switch]$DryRun,
    [int]$Limit = 50
)

$ErrorActionPreference = "Continue"
$Root = "D:\AgentesGuille"
$LogFile = "$Root\reports\daily-scheduler-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Set-Location -LiteralPath $Root
Write-Log "=== PC MIDI DAILY START (limit=$Limit, dryrun=$DryRun) ==="
Write-Log "Python: $(python --version 2>&1)"

$SwarmArgs = @("swarm.py", "daily", "--limit", "$Limit")
if ($DryRun) { $SwarmArgs += "--dry-run" }

Write-Log "Comando: python $($SwarmArgs -join ' ')"
& python @SwarmArgs
Write-Log "Exit: $LASTEXITCODE"
Write-Log "=== PC MIDI DAILY END ==="

# Salir 0 siempre para no poner Task Scheduler en Failed por advertencias no criticas.
exit 0
