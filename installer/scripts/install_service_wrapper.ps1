# Run install_service.bat with elevation and show result to the user.
# Called from Inno Setup [Run] when "Install as Windows Service" is checked.
# Usage: .\install_service_wrapper.ps1 -InstallDir "C:\Program Files\Planner"
# Messages in English for reliable display (no encoding issues).

param(
    [Parameter(Mandatory = $true)]
    [string] $InstallDir
)

Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$ErrorActionPreference = 'Stop'
$exitCode = -1
$batPath = Join-Path $InstallDir 'scripts\install_service.bat'
$nssmPath = Join-Path $InstallDir 'nssm\nssm.exe'

if (-not (Test-Path $batPath)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Service install script not found: $batPath",
        'Planner - Service install',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    )
    exit 1
}

if (-not (Test-Path $nssmPath)) {
    [System.Windows.Forms.MessageBox]::Show(
        "NSSM is not included in this installer. Windows Service option is unavailable.`n`nTo enable service install, rebuild the installer after running: installer\scripts\download_nssm.ps1",
        'Planner - Service install',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    )
    exit 0
}

try {
    $proc = Start-Process -FilePath $batPath -ArgumentList "`"$InstallDir`"" -WorkingDirectory $InstallDir -Wait -PassThru -NoNewWindow
    $exitCode = $proc.ExitCode
    if ($exitCode -eq 0) {
        [System.Windows.Forms.MessageBox]::Show(
            "Planner service was installed and started successfully. It will run when Windows starts.",
            'Planner - Service install',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
        exit 0
    }
} catch {
    $exitCode = -1
}

[System.Windows.Forms.MessageBox]::Show(
    "Service install failed (exit code: $exitCode).`n`nRun Planner manually from the installation folder.",
    'Planner - Service install',
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Warning
)
exit 1
