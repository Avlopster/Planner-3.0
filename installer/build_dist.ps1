# Prepare installer_sources for Inno Setup: copy app (Planner 3.0), ensure python/ exists, copy scripts.
# Run from Planner 3.0 root: .\installer\build_dist.ps1
# Prerequisite: run installer\scripts\download_python_embedded.ps1 to fill installer_sources\python

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$SourcesDir = Join-Path $RepoRoot "installer_sources"
$AppSrc = $RepoRoot
$AppDest = Join-Path $SourcesDir "app"
$PythonDir = Join-Path $SourcesDir "python"
$ScriptsSrc = Join-Path $ScriptDir "scripts"
$ScriptsDest = Join-Path $SourcesDir "scripts"

$ExcludeDirs = @(
    "__pycache__",
    ".pytest_cache",
    ".git",
    "tests",
    ".cursor",
    "installer",
    "installer_sources"
)

if (-not (Test-Path (Join-Path $AppSrc "Planner.py"))) {
    Write-Error "Planner.py not found in app source: $AppSrc"
}

# Create installer_sources
New-Item -ItemType Directory -Path $SourcesDir -Force | Out-Null
New-Item -ItemType Directory -Path $ScriptsDest -Force | Out-Null

# Copy app (excluding listed dirs)
Write-Host "Copying app from Planner 3.0 to installer_sources\app ..."
if (Test-Path $AppDest) { Remove-Item $AppDest -Recurse -Force }
New-Item -ItemType Directory -Path $AppDest -Force | Out-Null

$all = Get-ChildItem -Path $AppSrc -Force
foreach ($item in $all) {
    if ($item.Name -in $ExcludeDirs) { continue }
    Copy-Item -Path $item.FullName -Destination (Join-Path $AppDest $item.Name) -Recurse -Force
}

# config.toml: copy to config_default for onlyifdoesntexist at install; remove from app so it won't overwrite on update
$StreamlitConfig = Join-Path $AppDest ".streamlit\config.toml"
$ConfigDefaultDir = Join-Path $SourcesDir "config_default"
if (Test-Path $StreamlitConfig) {
    New-Item -ItemType Directory -Path $ConfigDefaultDir -Force | Out-Null
    Copy-Item -Path $StreamlitConfig -Destination (Join-Path $ConfigDefaultDir "config.toml") -Force
    Remove-Item -Path $StreamlitConfig -Force
    Write-Host "config.toml moved to config_default (preserved on update)"
}

Write-Host "App copy done."

# Check Python Embedded
if (-not (Test-Path (Join-Path $PythonDir "python.exe"))) {
    Write-Warning "installer_sources\python\python.exe not found. Run: .\installer\scripts\download_python_embedded.ps1"
} else {
    Write-Host "Python Embedded found in installer_sources\python"
}

# Copy scripts to installer_sources root (for {app}) and to installer_sources/scripts (for {app}/scripts)
$RootScripts = @("start_planner.bat", "setup_venv.bat")
foreach ($name in $RootScripts) {
    $src = Join-Path $ScriptsSrc $name
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $SourcesDir $name) -Force
        Write-Host "Copied $name to installer_sources\"
    }
}

$ScriptsToCopy = @("install_service.bat", "install_service_wrapper.ps1", "uninstall_service.bat", "create_desktop_url.ps1", "check_planner_service.ps1", "stop_planner_service.ps1", "start_planner_service.ps1")
foreach ($name in $ScriptsToCopy) {
    $src = Join-Path $ScriptsSrc $name
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $ScriptsDest $name) -Force
        Write-Host "Copied $name to installer_sources\scripts\"
    }
}

Write-Host "build_dist.ps1 done. installer_sources is ready for Inno Setup."
