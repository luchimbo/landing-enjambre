<#
.SYNOPSIS
    Pipeline semanal: research -> generate -> lead-magnets -> validate ->
    build -> deploy -> geo-audit -> distribution generate.
    Programado via Windows Task Scheduler: Lunes 10:00 ART.

.NOTES
    Fase 1 es hard-block: si falla, aborta y escribe reporte en reports/.
    Fases 2 y 3 son soft: un fallo no impide continuar.
#>
param(
    [switch]$DryRun,
    [int]$Limit = 5,
    [string]$BaseUrl = "https://blog.pcmidicenter.com"
)

$ErrorActionPreference = "Continue"
$Root = "D:\AgentesGuille"
$LogFile = "$Root\reports\weekly-scheduler-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

function Write-Log {
    param([string]$Message)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Set-Location -LiteralPath $Root
Write-Log "=== PC MIDI WEEKLY START (limit=$Limit, dryrun=$DryRun, baseUrl=$BaseUrl) ==="
Write-Log "Python: $(python --version 2>&1)"

# Fase 1: pipeline semanal principal -- si falla, aborta todo
$WeeklyArgs = @("swarm.py", "weekly", "--limit", "$Limit", "--base-url", $BaseUrl)
if ($DryRun) { $WeeklyArgs += "--dry-run" }

Write-Log "Fase 1: weekly core"
& python @WeeklyArgs
if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR Fase 1 (exit $LASTEXITCODE) -- abortando fases 2 y 3"
    exit $LASTEXITCODE
}
Write-Log "Fase 1: OK"

# Fase 2: geo-audit -- consulta 7 LLMs para monitoreo competitivo (soft)
Write-Log "Fase 2: geo-audit"
& python swarm.py geo-audit --limit 0
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARN Fase 2: geo-audit fallo (exit $LASTEXITCODE) -- continua"
} else {
    Write-Log "Fase 2: OK"
}

# Fase 3: distribution generate para landings recien desplegadas (soft)
Write-Log "Fase 3: distribution generate"
$DistArgs = @("swarm.py", "distribution", "generate", "--limit", "10", "--since-last-deploy")
if ($DryRun) { $DistArgs += "--dry-run" }
& python @DistArgs
if ($LASTEXITCODE -ne 0) {
    Write-Log "WARN Fase 3: distribution generate fallo (exit $LASTEXITCODE)"
} else {
    Write-Log "Fase 3: OK"
}

Write-Log "=== PC MIDI WEEKLY END ==="
exit 0
