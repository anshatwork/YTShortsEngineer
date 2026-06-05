@echo off
REM ============================================================================
REM  YTShortsEnginer — one-shot dev launcher
REM  Opens two new cmd windows:
REM    1. Backend  — uvicorn FastAPI on  http://127.0.0.1:8000
REM    2. Frontend — Next.js dev server  http://localhost:3000
REM  Each Ctrl+C kills only its own service. Close a window to stop it.
REM ============================================================================

setlocal

set "ROOT=%~dp0"

echo Launching backend (port 8000)...
start "YTShorts Backend" cmd /k "cd /d %ROOT% && python -m uvicorn agents.long_to_shorts.api.app:app --reload --host 127.0.0.1 --port 8000 --log-level info"

REM Give uvicorn a few seconds to bind before the frontend starts polling
timeout /t 3 /nobreak >nul

echo Launching frontend (port 3000)...
start "YTShorts Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo.
echo  Backend  : http://localhost:8000/health
echo  API docs : http://localhost:8000/docs
echo  Frontend : http://localhost:3000
echo.

endlocal
