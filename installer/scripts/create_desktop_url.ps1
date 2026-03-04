# Create Planner.url on desktop (variant C: InternetShortcut).
# Usage: .\create_desktop_url.ps1 -DesktopPath "C:\Users\...\Desktop" [-LogPath "path\to\install.log"]

param(
    [Parameter(Mandatory = $true)]
    [string] $DesktopPath,
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

try {
    Write-InstallLog 'create_desktop_url.ps1 started'
    $UrlPath = Join-Path $DesktopPath "Planner.url"
    $Content = @"
[InternetShortcut]
URL=http://localhost:8501
"@
    [System.IO.File]::WriteAllText($UrlPath, $Content, [System.Text.Encoding]::Default)
    Write-InstallLog 'create_desktop_url.ps1 completed'
} catch {
    Write-InstallLog "create_desktop_url.ps1 failed: $_"
    throw
}
