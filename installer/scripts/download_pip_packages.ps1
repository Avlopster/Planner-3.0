# Download get-pip.py and all pip dependencies (wheels) for offline installation.
# Run from Planner 3.0 root (or anywhere; paths are resolved relative to this script).
# Creates installer_sources\pip_offline\get-pip.py and installer_sources\pip_offline\wheels\*.whl
# Usage: .\installer\scripts\download_pip_packages.ps1 [-RequirementsPath "path\to\requirements.txt"]

param(
    [string] $RequirementsPath
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DefaultRequirements = Join-Path $RepoRoot "requirements.txt"
$ReqPath = if ($RequirementsPath) { $RequirementsPath } else { $DefaultRequirements }
$OutDir = Join-Path $RepoRoot "installer_sources\pip_offline"
$WheelsDir = Join-Path $OutDir "wheels"

if (-not (Test-Path $ReqPath)) {
    Write-Error "Requirements file not found: $ReqPath"
}

# Resolve Python for download: prefer launcher py, then system python.
$PythonExe = $null
try {
    $pyOut = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($pyOut) { $PythonExe = $pyOut.Trim() }
} catch {}
if (-not $PythonExe) {
    try {
        $pyOut = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($pyOut) { $PythonExe = $pyOut.Trim() }
    } catch {}
}
if (-not $PythonExe) {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Write-Error "Python 3.10+ not found. Install Python or use the Python launcher (py)."
}

Write-Host "Using Python: $PythonExe"
$pipVersion = & $PythonExe -m pip --version 2>$null
if (-not $pipVersion) {
    Write-Error "pip not available for $PythonExe. Install pip and retry."
}
Write-Host $pipVersion

New-Item -ItemType Directory -Path $WheelsDir -Force | Out-Null

# 1) get-pip.py
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$GetPipPath = Join-Path $OutDir "get-pip.py"
Write-Host "Downloading get-pip.py to $GetPipPath ..."
Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipPath -UseBasicParsing
Write-Host "get-pip.py done."

# 2) virtualenv (required by setup_venv.bat before creating venv)
Write-Host "Downloading virtualenv and dependencies to $WheelsDir ..."
$p = Start-Process -FilePath $PythonExe -ArgumentList '-m', 'pip', 'download', 'virtualenv', '-d', $WheelsDir, '--no-cache-dir' -Wait -NoNewWindow -PassThru
if ($p.ExitCode -ne 0) {
    Write-Error "pip download virtualenv failed (exit code $($p.ExitCode))."
}

# 3) app requirements and all transitive dependencies
Write-Host "Downloading requirements from $ReqPath and dependencies to $WheelsDir ..."
$p = Start-Process -FilePath $PythonExe -ArgumentList '-m', 'pip', 'download', '-r', $ReqPath, '-d', $WheelsDir, '--no-cache-dir' -Wait -NoNewWindow -PassThru
if ($p.ExitCode -ne 0) {
    Write-Error "pip download -r requirements.txt failed (exit code $($p.ExitCode))."
}

Write-Host "Done. Offline package cache: $OutDir"
Write-Host "  get-pip.py and wheels\\*.whl will be included in the installer for offline install."
Write-Host "  Versions are locked at download time from $ReqPath (stable snapshot for offline install)."

