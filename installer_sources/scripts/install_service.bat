@echo off
REM Register Planner as Windows service via NSSM. Requires NSSM on PATH or in app dir.
REM Usage: install_service.bat <InstallDir>
REM Example: install_service.bat "C:\Program Files\Planner"

set "INSTALLDIR=%~1"
if not defined INSTALLDIR exit /b 1

set "PYTHON=%INSTALLDIR%\venv\Scripts\python.exe"
set "ARGS=-m streamlit run Planner.py --server.port 8501"
set "WORKDIR=%INSTALLDIR%\app"
set "SERVICE_NAME=Planner"

set "NSSM=nssm"
where nssm >nul 2>&1 || set "NSSM=%INSTALLDIR%\nssm\nssm.exe"
if not exist "%NSSM%" (
    echo NSSM not found. Run installer\scripts\download_nssm.ps1 before building the installer.
    exit /b 1
)

"%NSSM%" stop %SERVICE_NAME% 2>nul
"%NSSM%" remove %SERVICE_NAME% confirm 2>nul
"%NSSM%" install %SERVICE_NAME% "%PYTHON%" "%ARGS%"
"%NSSM%" set %SERVICE_NAME% AppDirectory "%WORKDIR%"
"%NSSM%" set %SERVICE_NAME% AppEnvironmentExtra "PLANNER_DB_PATH=%INSTALLDIR%\data\resource_planner.db"
"%NSSM%" start %SERVICE_NAME%
