@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo Virtualenv not found. Run setup.cmd first.
  exit /b 1
)

.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8080

endlocal

