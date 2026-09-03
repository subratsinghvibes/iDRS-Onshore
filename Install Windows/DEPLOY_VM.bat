@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM Complete VM Deployment Script for iDRS
REM For Windows VM with Python 3.13.9 - IP: 10.212.64.16
REM ============================================================================

echo.
echo ============================================
echo iDRS - Complete VM Deployment
echo ============================================
echo.
echo This script will:
echo 1. Create Python virtual environment
echo 2. Install all dependencies from offline packages
echo 3. Setup the database
echo 4. Collect static files
echo 5. Create admin user
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul
echo.

REM Check Python
echo [STEP 1/6] Verifying Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.13.9 from python.org
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)
echo Python found:
python --version
echo.

REM Create virtual environment
echo [STEP 2/6] Creating virtual environment...
if exist ".venv" (
    echo Virtual environment already exists, skipping...
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully
)
echo.

REM Activate virtual environment
echo [STEP 3/6] Activating virtual environment...
call .venv\Scripts\activate.bat
echo.

REM Install packages
echo [STEP 4/6] Installing dependencies from offline packages...
echo This may take a few minutes...
echo.

REM Disable internet access for pip
set PIP_NO_INDEX=1
set PIP_RETRIES=0
set PIP_TIMEOUT=1

REM Install all packages from requirements.txt
python -m pip install --no-index --find-links=offline_packages -r requirements.txt

REM Configure pywin32
echo Configuring pywin32...
python .venv\Scripts\pywin32_postinstall.py -install 2>nul

echo.
echo Package installation complete!
echo.

REM Database setup
echo [STEP 5/6] Setting up database...
echo.
echo Choose database backend:
echo   1) PostgreSQL on 10.212.64.16 (RECOMMENDED for production)
echo   2) SQLite (development / fallback only)
echo.
set /p DB_CHOICE="Enter choice [1/2, default 1]: "
if "!DB_CHOICE!"=="2" (
    echo Setting up SQLite database...
    python manage.py migrate
    if errorlevel 1 (
        echo ERROR: Database migration failed!
        echo Full output is shown above - copy and share for support.
        pause
        exit /b 1
    )
) else (
    echo Launching PostgreSQL setup...
    call "%~dp0setup_postgres.bat"
    if errorlevel 1 (
        echo ERROR: PostgreSQL setup failed!
        pause
        exit /b 1
    )
    REM Migrations and static files already handled by setup_postgres.bat
    goto deployment_done
)
echo.

REM Collect static files
echo [STEP 6/6] Collecting static files...
python manage.py collectstatic --noinput
if errorlevel 1 (
    echo WARNING: Static files collection had issues.
    echo Full output above - copy and share for support.
)
echo.
:deployment_done

REM Create superuser
echo ============================================
echo Creating Admin User
echo ============================================
echo.
echo Please create an admin account for the application.
echo You will be prompted to enter:
echo   - Username (e.g., admin)
echo   - Email (optional, can leave blank)
echo   - Password (minimum 8 characters)
echo.
python manage.py createsuperuser
if errorlevel 1 (
    echo.
    echo Note: If a user already exists, this is normal.
)

echo.
echo ============================================
echo Deployment Complete!
echo ============================================
echo.
echo The iDRS application is now ready to use!
echo.
echo To start the server:
echo   "Install Windows\start_server.bat"
echo.
echo The application will be accessible at:
echo   - Local: http://localhost:8022
echo   - Network: http://10.212.64.16:8022
echo.
echo Default admin login URL:
echo   http://10.212.64.16:8022/admin
echo.
echo Press any key to exit...
pause >nul
