@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing_environment
if not exist ".venv\Scripts\pythonw.exe" goto missing_environment
if not exist "scripts\check_desktop.py" goto missing_files
if not exist "scripts\run_desktop.py" goto missing_files
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
".venv\Scripts\python.exe" "scripts\check_desktop.py"
if errorlevel 1 goto failed_check
start "" ".venv\Scripts\pythonw.exe" "scripts\run_desktop.py"
if errorlevel 1 goto failed_start
exit /b 0

:missing_environment
echo LapSim's .venv was not found. Run setup_lapsim.cmd first.
pause
exit /b 1

:missing_files
echo LapSim's desktop scripts are missing. Restore the checkout and rerun setup_lapsim.cmd.
pause
exit /b 1

:failed_check
echo LapSim could not launch. Review the check error above, then run setup_lapsim.cmd.
pause
exit /b 1

:failed_start
echo LapSim could not start its desktop process. Run setup_lapsim.cmd and try again.
pause
exit /b 1
