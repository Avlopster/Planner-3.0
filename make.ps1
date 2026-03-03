# Обёртка для make: вызывает make по полному пути (если make не в PATH)
$makeExe = "C:\Users\Art\AppData\Local\Microsoft\WinGet\Packages\ezwinports.make_Microsoft.Winget.Source_8wekyb3d8bbwe\bin\make.exe"
if (Get-Command make -ErrorAction SilentlyContinue) {
    & make @args
} elseif (Test-Path $makeExe) {
    & $makeExe @args
} else {
    Write-Error "make не найден. Установите: winget install ezwinports.make"
    exit 1
}
