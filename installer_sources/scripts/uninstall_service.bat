@echo off
REM Remove Planner Windows service (NSSM).
REM Usage: uninstall_service.bat [InstallDir]
REM If InstallDir is set, uses %InstallDir%\nssm\nssm.exe; otherwise nssm must be on PATH.
set "SERVICE_NAME=Planner"
set "INSTALLDIR=%~1"
set "NSSM=nssm"
if defined INSTALLDIR if exist "%INSTALLDIR%\nssm\nssm.exe" (
    set "NSSM=%INSTALLDIR%\nssm\nssm.exe"
    goto :run
)
where nssm >nul 2>&1 || goto :eof
:run
"%NSSM%" stop %SERVICE_NAME% 2>nul
"%NSSM%" remove %SERVICE_NAME% confirm 2>nul
