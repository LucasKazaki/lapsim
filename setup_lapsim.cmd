@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_lapsim.ps1"
set "setup_status=%errorlevel%"
echo.
if not "%setup_status%"=="0" echo Setup stopped with an error. Review the message above.
pause
exit /b %setup_status%
