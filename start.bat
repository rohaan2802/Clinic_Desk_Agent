@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtualenv...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv. Install Python 3.12+ and retry.
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

if not exist ".env" if exist ".env.example" copy /y ".env.example" ".env" >nul

".venv\Scripts\python.exe" run.py
exit /b %ERRORLEVEL%
