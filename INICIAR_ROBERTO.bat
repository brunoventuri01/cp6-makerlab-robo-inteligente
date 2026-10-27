@echo off
cd /d "%~dp0"
if exist "%~dp0python\pythonw.exe" (
  start "" "%~dp0python\pythonw.exe" "%~dp0iniciar.py"
  exit /b
)
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo O ambiente do Roberto nao foi encontrado. Consulte README.md.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0iniciar.py"
exit /b
