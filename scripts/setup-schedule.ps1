<#
.SYNOPSIS
    Registra las tareas programadas del enjambre PC MIDI en Windows Task Scheduler.
    No requiere Administrator si el usuario tiene permisos normales.
#>
param(
    [string]$Root = "D:\AgentesGuille"
)

$s  = "$Root\scripts"
$ps = "powershell.exe -NonInteractive -ExecutionPolicy Bypass -File"

Write-Host ""
Write-Host "=== Setup PC MIDI Task Scheduler ==="
Write-Host ""

$ok = $true

# -- PC MIDI Weekly: solo lunes 10:00 ART ------------------------------------
Write-Host "Registrando PC MIDI Weekly (lunes 10:00)..."
schtasks /create /tn "PC MIDI Weekly" /tr "$ps $s\weekly.ps1" /sc WEEKLY /d MON /st 10:00 /f
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR al registrar Weekly"; $ok = $false } else { Write-Host "  OK" }

# -- PC MIDI Daily Monday: lunes 13:30 (despues del weekly) ------------------
Write-Host "Registrando PC MIDI Daily Monday (lunes 13:30)..."
schtasks /create /tn "PC MIDI Daily Monday" /tr "$ps $s\daily.ps1" /sc WEEKLY /d MON /st 13:30 /f
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR al registrar Daily Monday"; $ok = $false } else { Write-Host "  OK" }

# -- PC MIDI Daily: mar-vie 10:30 --------------------------------------------
Write-Host "Registrando PC MIDI Daily (mar-vie 10:30)..."
schtasks /create /tn "PC MIDI Daily" /tr "$ps $s\daily.ps1" /sc WEEKLY /d TUE,WED,THU,FRI /st 10:30 /f
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR al registrar Daily Tue-Fri"; $ok = $false } else { Write-Host "  OK" }

# -- PC MIDI Engagement: lun-vie 16:30 ---------------------------------------
Write-Host "Registrando PC MIDI Engagement (lun-vie 16:30)..."
schtasks /create /tn "PC MIDI Engagement" /tr "$ps $s\engagement.ps1" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:30 /f
if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR al registrar Engagement"; $ok = $false } else { Write-Host "  OK" }

# -- Deshabilitar tareas viejas de Agent2 ------------------------------------
Write-Host ""
Write-Host "Deshabilitando tareas antiguas de Agent2..."
schtasks /change /tn "PC MIDI Agent2 Validate Daily" /disable 2>$null
schtasks /change /tn "PC MIDI Agent2 Generate Daily" /disable 2>$null
Write-Host "  OK (o no existian)"

# -- Verificacion final -------------------------------------------------------
Write-Host ""
Write-Host "=== Tareas PC MIDI registradas ==="
schtasks /query /fo TABLE /nh | Select-String "PC MIDI"

Write-Host ""
if ($ok) {
    Write-Host "Setup completo. Los agentes correran automaticamente de lunes a viernes."
} else {
    Write-Host "Hubo errores. Revisa los mensajes de arriba."
}
Write-Host ""
