@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo Crie o ambiente .venv e instale requirements.txt primeiro.
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -u run_daily_pipeline.py
exit /b %errorlevel%
