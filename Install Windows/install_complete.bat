@echo off
REM ============================================================================
REM Complete Offline Installation - All Dependencies
REM This installs EVERYTHING needed for the application
REM ============================================================================

echo ========================================
echo COMPLETE OFFLINE INSTALLATION
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    pause
    exit /b 1
)

python --version
echo.

REM Create/activate virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

REM Set offline mode
set PIP_NO_INDEX=1
set PIP_RETRIES=0
set PIP_TIMEOUT=1

echo ========================================
echo Installing ALL Packages
echo ========================================
echo.
echo This will take 2-3 minutes...
echo.

REM Install EVERYTHING from offline_packages
for %%f in (offline_packages\*-py3-none-any.whl offline_packages\*-py2.py3-none-any.whl offline_packages\*-win_amd64.whl offline_packages\*-abi3-win_amd64.whl) do (
    if exist "%%f" (
        echo Installing %%~nxf...
        python -m pip install --no-index --find-links=offline_packages "%%f" 2>nul
    )
)

echo.
echo ========================================
echo Configuring pywin32
echo ========================================
python .venv\Scripts\pywin32_postinstall.py -install 2>nul
echo pywin32 configured.

echo.
echo ========================================
echo Verifying Critical Packages
echo ========================================
echo.

python -c "import django; print('✓ Django:', django.get_version())" || echo ✗ Django FAILED
python -c "import rest_framework; print('✓ Django REST Framework')" || echo ✗ REST Framework FAILED
python -c "import pandas; print('✓ Pandas')" || echo ✗ Pandas FAILED
python -c "import numpy; print('✓ NumPy')" || echo ✗ NumPy FAILED
python -c "from ortools.sat.python import cp_model; print('✓ OR-Tools')" || echo ✗ OR-Tools FAILED
python -c "import openpyxl; print('✓ openpyxl')" || echo ✗ openpyxl FAILED
python -c "import plotly; print('✓ Plotly')" || echo ✗ Plotly FAILED
python -c "import whitenoise; print('✓ WhiteNoise')" || echo ✗ WhiteNoise FAILED
python -c "import ldap3; print('✓ LDAP3')" || echo ✗ LDAP3 FAILED
python -c "import imageio; print('✓ ImageIO')" || echo ✗ ImageIO FAILED
python -c "import moviepy; print('✓ MoviePy')" || echo ✗ MoviePy FAILED
python -c "import PIL; print('✓ Pillow')" || echo ✗ Pillow FAILED

echo.
echo ========================================
echo All Installed Packages
echo ========================================
python -m pip list

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next: Run setup_database.bat
echo.
pause
