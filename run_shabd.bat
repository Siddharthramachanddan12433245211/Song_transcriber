@echo off
rem Shabd — Offline Subtitle Studio launcher
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo First-time setup: creating the app environment. This runs once...
  py -m venv .venv
  if errorlevel 1 goto :err
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :err
)

start "" ".venv\Scripts\pythonw.exe" -m shabd.gui
exit /b 0

:err
echo.
echo Setup failed. Is Python installed? See README.md for help.
pause
exit /b 1
