# Stop Planner Windows service. Requires administrator rights.
# Usage: run with elevation (e.g. Start-Process -Verb RunAs)
# .\stop_planner_service.ps1

$ErrorActionPreference = 'Stop'
$svc = Get-Service -Name 'Planner' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    Stop-Service -Name 'Planner' -Force
    Write-Host 'Planner service stopped.'
}
exit 0

