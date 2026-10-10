@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup_lapsim.cmd before building.
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.lock
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" scripts\build_windows.py %*
exit /b %errorlevel%
