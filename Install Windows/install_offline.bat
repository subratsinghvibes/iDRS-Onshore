@echo off
REM ============================================================================
REM Offline Installation Script for Interactive Drilling Rig Scheduler
REM For Windows with Python 3.13.5 (No Internet Required)
REM ============================================================================

echo ========================================
echo IDRS Offline Installation
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.13.5 first.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python Version: %PYTHON_VERSION%
echo.

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
) else (
    echo Virtual environment already exists.
)
echo.

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)
echo.

REM Set environment variable to prevent internet access
echo Setting offline mode...
set PIP_NO_INDEX=1
set PIP_FIND_LINKS=offline_packages
echo.

REM Upgrade pip from offline packages if available
echo Upgrading pip (skipping - not needed)...
echo.

REM Install all packages from offline_packages directory
echo Installing packages from offline_packages directory...
echo This may take several minutes...
echo.

REM Core Django and web framework
python -m pip install --no-index --find-links=offline_packages --no-deps Django==5.1.5
python -m pip install --no-index --find-links=offline_packages --no-deps djangorestframework==3.15.2
python -m pip install --no-index --find-links=offline_packages --no-deps django-cors-headers==4.6.0
python -m pip install --no-index --find-links=offline_packages --no-deps whitenoise

REM Database
python -m pip install --no-index --find-links=offline_packages --no-deps psycopg2-binary

REM Data processing
python -m pip install --no-index --find-links=offline_packages --no-deps pandas
python -m pip install --no-index --find-links=offline_packages --no-deps numpy
python -m pip install --no-index --find-links=offline_packages --no-deps ortools
python -m pip install --no-index --find-links=offline_packages --no-deps openpyxl==3.1.5
python -m pip install --no-index --find-links=offline_packages --no-deps plotly==5.24.1
python -m pip install --no-index --find-links=offline_packages --no-deps Pillow

REM LDAP and environment
python -m pip install --no-index --find-links=offline_packages --no-deps ldap3
python -m pip install --no-index --find-links=offline_packages --no-deps python-dotenv==1.0.1
python -m pip install --no-index --find-links=offline_packages --no-deps pywin32

REM Video processing (optional but recommended)
python -m pip install --no-index --find-links=offline_packages --no-deps decorator
python -m pip install --no-index --find-links=offline_packages --no-deps imageio
python -m pip install --no-index --find-links=offline_packages --no-deps imageio-ffmpeg
python -m pip install --no-index --find-links=offline_packages --no-deps moviepy
python -m pip install --no-index --find-links=offline_packages --no-deps proglog
python -m pip install --no-index --find-links=offline_packages --no-deps tqdm
python -m pip install --no-index --find-links=offline_packages --no-deps colorama

REM Install all remaining dependencies
echo.
echo Installing remaining dependencies...
python -m pip install --no-index --find-links=offline_packages asgiref sqlparse python-dateutil pytz tzdata et-xmlfile tenacity packaging absl-py protobuf typing-extensions immutabledict six pyasn1

if errorlevel 1 (
    echo WARNING: Some packages may have failed to install.
    echo Checking installation status...
    python -m pip list
)
echo.

REM Run pywin32 post-install script
echo Configuring pywin32...
python .venv\Scripts\pywin32_postinstall.py -install
echo.

echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Run 'setup_windows.bat' to initialize the database
echo 2. Run 'start_server.bat' to start the Django server
echo.
pause
