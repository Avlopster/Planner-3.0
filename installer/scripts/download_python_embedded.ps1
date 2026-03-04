# Download Python Embedded for Windows and extract to installer_sources/python.
# Run from repo root or pass -OutputDir. Used before building the installer.
# Usage: .\download_python_embedded.ps1 [-Version "3.12.12"] [-OutputDir "D:\Dev\Planner\installer_sources\python"]

param(
    [string] $Version = "3.12.10",
    [string] $Arch = "amd64",
    [string] $OutputDir
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DefaultOutput = Join-Path $RepoRoot "installer_sources\python"
$TargetDir = if ($OutputDir) { $OutputDir } else { $DefaultOutput }

$BaseUrl = "https://www.python.org/ftp/python/$Version"
$ZipName = "python-$Version-embed-$Arch.zip"
$ZipUrl = "$BaseUrl/$ZipName"
$TempZip = Join-Path $env:TEMP $ZipName

Write-Host "Downloading $ZipUrl ..."
Invoke-WebRequest -Uri $ZipUrl -OutFile $TempZip -UseBasicParsing

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}
Write-Host "Extracting to $TargetDir ..."
Expand-Archive -Path $TempZip -DestinationPath $TargetDir -Force
Remove-Item $TempZip -Force -ErrorAction SilentlyContinue
Write-Host "Done. Python Embedded $Version is in $TargetDir"
