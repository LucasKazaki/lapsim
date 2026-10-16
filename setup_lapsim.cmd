@echo off
setlocal
if exist "%~dp0.venv\Scripts\python.exe" goto existing
where py >nul 2>nul
if not errorlevel 1 goto launcher
python -X utf8 "%~dp0scripts\bootstrap.py" %*
set "setup_status=%errorlevel%"
goto finish
:launcher
py -3 -X utf8 "%~dp0scripts\bootstrap.py" %*
set "setup_status=%errorlevel%"
goto finish
:existing
"%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0scripts\bootstrap.py" %*
set "setup_status=%errorlevel%"
:finish
echo.
if not "%setup_status%"=="0" echo Setup stopped with an error. Review the message above.
pause
exit /b %setup_status%
