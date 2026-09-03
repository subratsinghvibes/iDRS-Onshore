@echo off
REM ============================================================================
REM Simplified Offline Installation Script for Windows VM
REM Supports Python 3.13.9 - Installs all dependencies from local wheels
REM ============================================================================

echo ========================================
echo IDRS Offline Installation (Simplified)
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.13.9 first.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Create virtual environment if needed
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat
echo.

REM Disable all internet access for pip
set PIP_NO_INDEX=1
set PIP_RETRIES=0
set PIP_TIMEOUT=1

echo ========================================
echo Installing Dependencies (Step 1/2)
echo ========================================
echo.

REM Install base dependencies first
echo [1/5] Installing base dependencies...
python -m pip install --no-index --find-links=offline_packages asgiref sqlparse typing-extensions
if errorlevel 1 echo WARNING: Base dependencies had issues

echo [2/5] Installing Django...
python -m pip install --no-index --find-links=offline_packages Django
if errorlevel 1 echo WARNING: Django installation had issues

echo [3/5] Installing Django extensions...
python -m pip install --no-index --find-links=offline_packages djangorestframework django-cors-headers
if errorlevel 1 echo WARNING: Django extensions had issues

echo [4/5] Installing data processing dependencies...
python -m pip install --no-index --find-links=offline_packages six python-dateutil pytz tzdata
if errorlevel 1 echo WARNING: Date/time dependencies had issues

echo [5/5] Installing numeric libraries...
python -m pip install --no-index --find-links=offline_packages numpy pandas
if errorlevel 1 echo WARNING: Numeric libraries had issues

echo.
echo ========================================
echo Installing Main Packages (Step 2/2)
echo ========================================
echo.

echo [1/8] Installing OR-Tools dependencies...
python -m pip install --no-index --find-links=offline_packages protobuf absl-py immutabledict
if errorlevel 1 echo WARNING: OR-Tools dependencies had issues

echo [2/8] Installing OR-Tools...
python -m pip install --no-index --find-links=offline_packages ortools
if errorlevel 1 echo WARNING: ortools installation had issues

echo [3/8] Installing Excel support...
python -m pip install --no-index --find-links=offline_packages et-xmlfile openpyxl
if errorlevel 1 echo WARNING: openpyxl installation had issues

echo [4/8] Installing visualization...
python -m pip install --no-index --find-links=offline_packages packaging tenacity plotly
if errorlevel 1 echo WARNING: plotly installation had issues

echo [5/8] Installing utilities (includes PostgreSQL drivers)...
python -m pip install --no-index --find-links=offline_packages python-dotenv psycopg2-binary dj-database-url
if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: Utilities installation failed!
    echo.
    echo Expected wheels in offline_packages\:
    echo   python_dotenv-1.0.1-py3-none-any.whl
    echo   psycopg2_binary-2.9.11-cp313-cp313-win_amd64.whl
    echo   dj_database_url-3.1.2-py3-none-any.whl
    echo.
    echo Full pip output is shown above - copy and share for support.
    echo ============================================================
    pause
    exit /b 1
)

echo [6/8] Installing static file server...
python -m pip install --no-index --find-links=offline_packages whitenoise
if errorlevel 1 echo WARNING: whitenoise installation had issues

echo [7/8] Installing Windows support...
python -m pip install --no-index --find-links=offline_packages pywin32
if errorlevel 1 echo WARNING: pywin32 installation had issues

echo [8/9] Installing video processing (REQUIRED)...
python -m pip install --no-index --find-links=offline_packages decorator imageio imageio-ffmpeg moviepy proglog tqdm colorama Pillow ldap3 pyasn1
if errorlevel 1 (
    echo ERROR: Video processing packages failed to install!
    echo Video tutorials feature requires these packages.
    echo Please check offline_packages folder for missing files.
    pause
)

echo [9/9] Checking FFmpeg installation...
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo.
    echo ========================================
    echo WARNING: FFmpeg is NOT installed!
    echo ========================================
    echo.
    echo FFmpeg is REQUIRED for video tutorial features.
    echo.
    echo To install FFmpeg:
    echo 1. Run: download_ffmpeg.bat
    echo 2. Then run: install_ffmpeg.bat (as Administrator)
    echo.
    echo Or install manually:
    echo 1. Download from: https://github.com/BtbN/FFmpeg-Builds/releases
    echo 2. Extract and add to system PATH
    echo.
    set /p CONTINUE="Continue without FFmpeg? (Y/N): "
    if /i not "!CONTINUE!"=="Y" (
        echo Installation cancelled.
        pause
        exit /b 1
    )
    echo.
    echo WARNING: Video processing will not work without FFmpeg!
    echo.
) else (
    echo FFmpeg is installed:
    ffmpeg -version | findstr "ffmpeg version"
    echo.
)

echo.
echo ========================================
echo Configuring pywin32
echo ========================================
python .venv\Scripts\pywin32_postinstall.py -install 2>nul
echo.

echo ========================================
echo Verifying Installation
echo ========================================
echo.
echo Installed packages:
python -m pip list
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
