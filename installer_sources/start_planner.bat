@echo off
setlocal
set "INSTALLDIR=%~dp0"
set "INSTALLDIR=%INSTALLDIR:~0,-1%"

REM Use only the app venv: avoid system Python (e.g. C:\Python312) when it is on PATH
set "VENV=%INSTALLDIR%\venv"
set "PATH=%VENV%\Scripts;%VENV%\Library\bin;%PATH%"
set "VIRTUAL_ENV=%VENV%"

set "PLANNER_DB_PATH=%INSTALLDIR%\data\resource_planner.db"
if not exist "%INSTALLDIR%\data" mkdir "%INSTALLDIR%\data"

cd /d "%INSTALLDIR%\app"
"%VENV%\Scripts\python.exe" -m streamlit run Planner.py --server.port 8501

endlocal
