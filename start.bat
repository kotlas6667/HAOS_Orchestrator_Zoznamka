@echo off
cd /d "%~dp0"

echo Starting HAOS Orchestrator in development mode...

:: Create data directories if they don't exist
mkdir data\orchestrator 2>nul
mkdir data\orchestrator\logs 2>nul
mkdir data\orchestrator\config 2>nul
mkdir data\orchestrator\tokens 2>nul

:: Copy example config if not exists
if not exist .env (
    copy .env.example .env >nul 2>&1
)

echo Starting server on http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
pause
