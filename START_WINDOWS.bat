@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "PY=python") else (set "PY=py -3.11")
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 (echo Python 3.11 required. & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed. & pause & exit /b 1)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
