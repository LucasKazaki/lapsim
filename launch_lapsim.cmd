@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" goto missing_environment
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
start "" ".venv\Scripts\pythonw.exe" -m lapsim.ui
exit /b 0

:missing_environment
echo LapSim's .venv was not found. Open this folder in VS Code and run the setup first.
pause
