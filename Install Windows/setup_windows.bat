@echo off
REM ============================================
REM Interactive Drilling Rig Scheduler (iDRS)
REM Windows Deployment Setup Script
REM ============================================

echo.
echo ====================================
echo iDRS - Windows Deployment Setup
echo ====================================
echo.

REM Check Python version
python --version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python 3.13.9 and add it to PATH.
    pause
    exit /b 1
)

echo.
echo [1/5] Creating virtual environment...
python -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create virtual environment!
    pause
    exit /b 1
)

echo.
echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo [3/5] Checking pip version...
REM Skip pip upgrade to avoid internet access
echo Pip version:
python -m pip --version

echo.
echo [4/5] Verifying installed packages...
REM All packages should already be installed from install_offline_simple.bat
python -m pip list | findstr /C:"Django" /C:"djangorestframework" /C:"pandas" /C:"ortools"
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Some packages may be missing. Run install_offline_simple.bat first.
    pause
)

echo.
echo [5/5] Running migrations...
python manage.py migrate
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Database migration failed!
    pause
    exit /b 1
)

echo.
echo [6/6] Collecting static files...
python manage.py collectstatic --noinput
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Static files collection had issues
)

echo.
echo ====================================
echo Setup Complete!
echo ====================================
echo.
echo Next steps:
echo 1. Update CSRF_TRUSTED_ORIGINS in drilling_scheduler\settings.py with your VM IP
echo 2. Create a superuser: python manage.py createsuperuser
echo 3. Start the server: start_server.bat
echo.

pause
