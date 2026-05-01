@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  python -m venv .venv
)

.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
)

.venv\Scripts\alembic upgrade head

echo.
echo Setup complete.
echo Next: run.cmd
endlocal

