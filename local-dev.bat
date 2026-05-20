@echo off
REM VSKS_CRM - локальный запуск в один клик
REM Использование: local-dev.bat [up|down|restart|logs|psql]

setlocal
cd /d "%~dp0"

if "%1"=="" goto :up
if "%1"=="up" goto :up
if "%1"=="down" goto :down
if "%1"=="restart" goto :restart
if "%1"=="logs" goto :logs
if "%1"=="psql" goto :psql
if "%1"=="frontend" goto :frontend
goto :help

:up
echo === [VSKS_CRM local] starting db + backend ===
docker compose up -d db backend
if errorlevel 1 (
    echo.
    echo [ERROR] docker compose failed. Is Docker Desktop running?
    pause
    exit /b 1
)
echo.
echo Waiting 5s for backend to settle...
timeout /t 5 /nobreak >nul
docker ps --filter "name=vsks" --format "table {{.Names}}\t{{.Status}}"
echo.
echo Backend  : http://localhost:8000/docs
echo Frontend : run "local-dev.bat frontend" in ANOTHER terminal
echo.
goto :eof

:down
echo === [VSKS_CRM local] stopping ===
docker compose down
goto :eof

:restart
echo === [VSKS_CRM local] restart backend (after Python changes) ===
docker compose restart backend
timeout /t 3 /nobreak >nul
docker logs vsks_crm-backend-1 --tail 10
goto :eof

:logs
docker logs vsks_crm-backend-1 -f --tail 50
goto :eof

:psql
docker exec -it vsks_crm-db-1 psql -U vsks -d vsks_crm
goto :eof

:frontend
cd frontend
if not exist "node_modules" (
    echo === [VSKS_CRM local] installing npm deps (first run) ===
    npm install
)
echo === [VSKS_CRM local] starting Vite dev server ===
echo Frontend will be available at http://localhost:3002
npm run dev
goto :eof

:help
echo VSKS_CRM local dev helper
echo.
echo Usage:
echo   local-dev.bat            ^| same as "up"
echo   local-dev.bat up         ^| start db + backend (Docker)
echo   local-dev.bat down       ^| stop everything
echo   local-dev.bat restart    ^| restart backend (after .py changes)
echo   local-dev.bat logs       ^| tail backend logs
echo   local-dev.bat psql       ^| open psql to local DB
echo   local-dev.bat frontend   ^| start Vite dev server (separate terminal)
echo.
echo Typical workflow:
echo   Terminal 1: local-dev.bat up
echo   Terminal 2: local-dev.bat frontend
echo   Open http://localhost:3002
