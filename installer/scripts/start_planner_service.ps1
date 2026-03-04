# Start Planner Windows service. Requires administrator rights.
# Usage: run with elevation (e.g. Start-Process -Verb RunAs)
# .\start_planner_service.ps1

$ErrorActionPreference = 'Stop'
$svc = Get-Service -Name 'Planner' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne 'Running') {
    Start-Service -Name 'Planner'
    Write-Host 'Planner service started.'
}
exit 0
