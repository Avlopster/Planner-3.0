# Check if Planner Windows service is running. Used by installer before install/upgrade.
# Exit codes: 0 = not running or not found, 1 = running
# Usage: .\check_planner_service.ps1

$ErrorActionPreference = 'SilentlyContinue'
$svc = Get-Service -Name 'Planner' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    exit 1
}
exit 0

