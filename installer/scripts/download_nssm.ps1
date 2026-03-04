# Download NSSM (Non-Sucking Service Manager) x64 to installer_sources\nssm.
# Include this so the installer can optionally register Planner as a Windows Service.
# Usage: .\download_nssm.ps1 [-OutputDir "D:\Dev\Planner\installer_sources\nssm"]

param(
    [string] $OutputDir
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DefaultOutput = Join-Path $RepoRoot "installer_sources\nssm"
$TargetDir = if ($OutputDir) { $OutputDir } else { $DefaultOutput }

# Pre-release recommended for Windows 10+ (avoids service startup issues per nssm.cc). Fallback: stable 2.24.
$Urls = @(
    "https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip",
    "https://nssm.cc/release/nssm-2.24.zip"
)
$ZipPath = Join-Path $env:TEMP "nssm-download.zip"

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

$downloaded = $false
foreach ($ZipUrl in $Urls) {
    $maxAttempts = 3
    $attempt = 0
    while ($attempt -lt $maxAttempts) {
        $attempt++
        try {
            Write-Host "Downloading NSSM from $ZipUrl (attempt $attempt/$maxAttempts) ..."
            Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing -TimeoutSec 60
            $downloaded = $true
            break
        } catch {
            Write-Warning "Download failed: $($_.Exception.Message)"
            if ($attempt -lt $maxAttempts) {
                $delay = 5
                Write-Host "Retrying in ${delay}s..."
                Start-Sleep -Seconds $delay
            }
        }
    }
    if ($downloaded) { break }
    Write-Host "Trying fallback URL..."
}
if (-not $downloaded) {
    Write-Error "Could not download NSSM from any source (503 or network error). Try again later or download manually from https://nssm.cc/download"
}

Write-Host "Extracting to $TargetDir ..."
$TempExtract = Join-Path $env:TEMP "nssm-extract"
if (Test-Path $TempExtract) { Remove-Item $TempExtract -Recurse -Force }
Expand-Archive -Path $ZipPath -DestinationPath $TempExtract -Force

# Pre-release: win64\nssm.exe or nssm-2.24-101-*\win64\nssm.exe. Stable 2.24: nssm64.exe (or in subdir).
$Win64Exe = $null
$candidates = @(
    (Join-Path $TempExtract "win64\nssm.exe"),
    (Join-Path $TempExtract "nssm-2.24-101-g897c7ad\win64\nssm.exe")
)
foreach ($p in $candidates) {
    if (Test-Path $p) { $Win64Exe = $p; break }
}
if (-not $Win64Exe) {
    $found = Get-ChildItem -Path $TempExtract -Recurse -Include "nssm.exe","nssm64.exe" -File | Select-Object -First 1
    if ($found) { $Win64Exe = $found.FullName }
}
if (-not $Win64Exe -or -not (Test-Path $Win64Exe)) {
    Write-Error "nssm.exe / nssm64.exe not found in archive. Check NSSM zip structure."
}
Copy-Item -Path $Win64Exe -Destination (Join-Path $TargetDir "nssm.exe") -Force
Remove-Item $TempExtract -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue

Write-Host "Done. NSSM x64 is in $TargetDir. Add installer_sources\nssm to the installer for the service option."
