@echo off
setlocal EnableDelayedExpansion
REM ============================================
REM Interactive Drilling Rig Scheduler (iDRS)
REM Database Setup Script
REM ============================================
REM NOTE: This script configures SQLite (development/fallback only).
REM       For the production PostgreSQL deployment on 10.212.64.16,
REM       use:  setup_postgres.bat
REM ============================================

echo.
echo ====================================
echo iDRS - Database Setup (SQLite)
echo ====================================
echo.
echo NOTE: This script uses SQLite (for development/testing).
echo For the production PostgreSQL deployment on 10.212.64.16,
echo run setup_postgres.bat instead.
echo.
set /p USE_PG="Use PostgreSQL instead of SQLite? (Y/N, default N): "
if /i "!USE_PG!"=="Y" (
    echo.
    echo Launching PostgreSQL setup...
    echo.
    call "%~dp0setup_postgres.bat"
    exit /b %ERRORLEVEL%
)
echo.

REM Activate virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please run install_offline_simple.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Verify Django is installed
python -c "import django" 2>nul
if errorlevel 1 (
    echo ERROR: Django is not installed!
    echo Please run install_offline_simple.bat first.
    pause
    exit /b 1
)

echo Django installation verified.
echo.

echo [1/3] Running database migrations...
python manage.py migrate
if errorlevel 1 (
    echo ERROR: Database migration failed!
    pause
    exit /b 1
)

echo.
echo [2/3] Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 (
    echo WARNING: Static files collection had issues
    echo This is not critical - you can continue.
)

echo.
echo [3/3] Creating superuser...
echo.
echo You will be prompted to create an admin account.
echo Username: (your choice, e.g., admin)
echo Password: (strong password)
echo.
python manage.py createsuperuser
if errorlevel 1 (
    echo.
    echo Note: If superuser already exists, this is normal.
    echo You can skip this step or use manage_users.bat later.
)

echo.
echo ====================================
echo Setup Complete!
echo ====================================
echo.
echo Your application is ready to use!
echo.
echo To start the server:
echo   start_server.bat
echo.
echo To access the application:
echo   http://localhost:8022
echo.
echo To manage users:
echo   manage_users.bat
echo.

pause
