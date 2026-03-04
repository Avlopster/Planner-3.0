# Download Microsoft Visual C++ 2015-2022 Redistributable (x64) to installer_sources\redist.
# Include this in the installer to avoid error 0xC00004BC when running Python on PCs without VC Redist.
# Usage: .\download_vc_redist.ps1 [-OutputDir "D:\Dev\Planner\installer_sources\redist"]

param(
    [string] $OutputDir
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DefaultOutput = Join-Path $RepoRoot "installer_sources\redist"
$TargetDir = if ($OutputDir) { $OutputDir } else { $DefaultOutput }
$ExeName = "vc_redist.x64.exe"
$TargetPath = Join-Path $TargetDir $ExeName

# Official Microsoft download (VS 2015-2022 x64)
$Url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

Write-Host "Downloading VC++ Redistributable (x64) to $TargetPath ..."
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}
Invoke-WebRequest -Uri $Url -OutFile $TargetPath -UseBasicParsing
Write-Host "Done. Add installer_sources\redist to the installer so VC Redist runs on the target PC (avoids 0xC00004BC)."
