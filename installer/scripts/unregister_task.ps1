# Remove Planner scheduled task (run on uninstall).
# Usage: .\unregister_task.ps1

$TaskName = 'Planner'
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
