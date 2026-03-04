# Register Planner to run at user logon (Task Scheduler).
# Usage: .\register_task.ps1 -InstallDir "C:\Program Files\Planner" [-LogPath "path\to\install.log"]
# On failure tries schtasks.exe fallback; logs and exits 1 so installer can show warning (installation continues).

param(
    [Parameter(Mandatory = $true)]
    [string] $InstallDir,
    [Parameter(Mandatory = $false)]
    [string] $LogPath
)

function Write-InstallLog {
    param([string] $Message)
    if (-not $LogPath) { return }
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] $Message"
    try {
        Add-Content -Path $LogPath -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch { }
}

# Make error string one line for readable log (ASCII-safe)
function Get-ErrorLine {
    param([string] $Text)
    if (-not $Text) { return 'no message' }
    $one = ($Text -replace "[\r\n]+", ' ').Trim()
    if ($one.Length -gt 200) { $one = $one.Substring(0, 200) + '...' }
    return $one
}

$TaskName = 'Planner'
$BatPath = Join-Path $InstallDir 'start_planner.bat'
$TaskDescription = 'Planner (Streamlit) - start at user logon'

if (-not (Test-Path $BatPath)) {
    Write-InstallLog "register_task.ps1 failed: start_planner.bat not found: $BatPath"
    Write-Error "start_planner.bat not found: $BatPath"
    exit 1
}

Write-InstallLog 'register_task.ps1 started'

$err1 = $null
$err2 = $null
$err3 = $null

# Method 1: Register-ScheduledTask with explicit Principal (no RunLevel Highest)
try {
    $Action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $InstallDir
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description $TaskDescription | Out-Null
    Write-InstallLog 'register_task.ps1 completed (Register-ScheduledTask with Principal)'
    exit 0
} catch {
    $err1 = Get-ErrorLine $_.Exception.Message
    Write-InstallLog "register_task.ps1 Method 1 failed: $err1"
}

# Method 2: Register-ScheduledTask without Principal (default principal)
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    $Action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $InstallDir
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description $TaskDescription | Out-Null
    Write-InstallLog 'register_task.ps1 completed (Register-ScheduledTask default principal)'
    exit 0
} catch {
    $err2 = Get-ErrorLine $_.Exception.Message
    Write-InstallLog "register_task.ps1 Method 2 failed: $err2"
}

# Method 3: schtasks.exe
function Invoke-SchtasksCreate {
    param([string[]] $ExtraArgs, [ref] $OutErr)
    schtasks /Query /TN $TaskName /FO LIST 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { schtasks /Delete /TN $TaskName /F 2>$null | Out-Null }
    $tr = "`"$BatPath`""
    $argList = @('/Create', '/TN', $TaskName, '/TR', $tr, '/SC', 'ONLOGON', '/RU', $env:USERNAME) + $ExtraArgs + @('/F')
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'schtasks.exe'
    $psi.Arguments = ($argList -join ' ')
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    try {
        $p = [System.Diagnostics.Process]::Start($psi)
        $stderr = $p.StandardError.ReadToEnd()
        $stdout = $p.StandardOutput.ReadToEnd()
        $p.WaitForExit()
        if ($p.ExitCode -eq 0) { return $true }
        $combined = ($stderr + " " + $stdout).Trim()
        $OutErr.Value = Get-ErrorLine $combined
        if (-not $OutErr.Value) { $OutErr.Value = "exit code $($p.ExitCode)" }
        Write-InstallLog "register_task.ps1 schtasks failed (exit $($p.ExitCode)): $($OutErr.Value)"
    } catch {
        $OutErr.Value = Get-ErrorLine $_.Exception.Message
        Write-InstallLog "register_task.ps1 schtasks exception: $($OutErr.Value)"
    }
    return $false
}

$err3ref = [ref] $null
if (Invoke-SchtasksCreate -OutErr $err3ref) {
    Write-InstallLog 'register_task.ps1 completed (schtasks)'
    exit 0
}
$err3 = $err3ref.Value

if (Invoke-SchtasksCreate -ExtraArgs @('/RL', 'LIMITED') -OutErr $err3ref) {
    Write-InstallLog 'register_task.ps1 completed (schtasks /RL LIMITED)'
    exit 0
}
$err3 = $err3ref.Value

# All methods failed: write readable summary in English
Write-InstallLog '--- AUTOSTART TASK REGISTRATION FAILED ---'
Write-InstallLog 'Method 1 (Register-ScheduledTask with Principal): ' + (if ($err1) { $err1 } else { 'not tried or unknown' })
Write-InstallLog 'Method 2 (Register-ScheduledTask default principal): ' + (if ($err2) { $err2 } else { 'not tried or unknown' })
Write-InstallLog 'Method 3 (schtasks.exe): ' + (if ($err3) { $err3 } else { 'not tried or unknown' })
Write-InstallLog 'Recommendation: Run the installer as Administrator (right-click PlannerSetup.exe) or create the task manually in Task Scheduler.'
exit 1
