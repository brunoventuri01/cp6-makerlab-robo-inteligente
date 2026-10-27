@echo off
cd /d "%~dp0"
if exist "%~dp0python\pythonw.exe" (
  start "" "%~dp0python\pythonw.exe" "%~dp0gravar_arduino.py"
  exit /b
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0gravar_arduino.py"
