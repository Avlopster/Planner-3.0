# Build PlannerSetup.exe with Inno Setup. Requires Inno Setup 6 installed.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$IssPath = Join-Path $ScriptDir "Planner.iss"

$isccPaths = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    "ISCC.exe"
)
$iscc = $null
foreach ($p in $isccPaths) {
    if ($p -eq "ISCC.exe") {
        $exe = Get-Command $p -ErrorAction SilentlyContinue
        if ($exe) { $iscc = $exe.Source; break }
    } elseif (Test-Path $p) {
        $iscc = $p
        break
    }
}
if (-not $iscc) {
    Write-Error "Inno Setup ISCC.exe not found. Install from: https://jrsoftware.org/isinfo.php or run: winget install JRSoftware.InnoSetup"
    exit 1
}
Write-Host "Using: $iscc"
& $iscc $IssPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$out = Join-Path $ScriptDir "output\PlannerSetup.exe"
Write-Host "Done. Installer: $out"
