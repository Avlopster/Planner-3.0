@echo off
REM Create venv and install dependencies. Called by Inno Setup after copying files.
REM Inno must run this with WorkingDirectory = {app}.
REM Python Embedded has no venv module: we use get-pip.py, then virtualenv, then create venv.
REM Usage: setup_venv.bat [update] - if "update" and venv exists, only pip install -r requirements.txt
setlocal
set "APP=%CD%"

if "%~1"=="update" (
    if not exist "%APP%\venv\Scripts\python.exe" (
        echo venv not found, cannot update
        exit /b 1
    )
    echo Updating pip packages...
    "%APP%\venv\Scripts\pip.exe" install -r "%APP%\app\requirements.txt" -q --upgrade
    if errorlevel 1 exit /b 1
    echo Venv update complete.
    endlocal
    exit /b 0
)

if not exist "%APP%\python\python.exe" (
    echo python\python.exe not found in %APP%
    exit /b 1
)

set "GET_PIP=%APP%\get-pip.py"
if not exist "%GET_PIP%" (
    echo Downloading get-pip.py...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GET_PIP%' -UseBasicParsing"
    if errorlevel 1 exit /b 1
)

set "SITEPACKAGES=%APP%\python\Lib\site-packages"
if not exist "%SITEPACKAGES%" mkdir "%SITEPACKAGES%"

echo Installing pip...
"%APP%\python\python.exe" "%GET_PIP%" -q --no-warn-script-location --target="%SITEPACKAGES%"
if errorlevel 1 exit /b 1
if not exist "%SITEPACKAGES%\pip\__main__.py" (
    echo ERROR: pip was not installed to %SITEPACKAGES%
    exit /b 1
)

echo Installing virtualenv...
"%APP%\python\python.exe" -c "import sys; sys.path.insert(0, r'%SITEPACKAGES%'); sys.argv = ['pip', 'install', 'virtualenv', '-q', '--no-warn-script-location']; import runpy; runpy.run_module('pip', run_name='__main__')"
if errorlevel 1 exit /b 1

echo Creating venv...
"%APP%\python\python.exe" -c "import sys; sys.path.insert(0, r'%SITEPACKAGES%'); sys.argv = ['virtualenv', r'%APP%\venv']; import runpy; runpy.run_module('virtualenv', run_name='__main__')"
if errorlevel 1 exit /b 1

echo Upgrading pip...
"%APP%\venv\Scripts\python.exe" -m pip install --upgrade pip -q
echo Installing requirements...
"%APP%\venv\Scripts\pip.exe" install -r "%APP%\app\requirements.txt" -q
if errorlevel 1 exit /b 1

echo Venv setup complete.
endlocal
exit /b 0
