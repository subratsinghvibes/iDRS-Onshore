@echo off
REM ============================================================================
REM Package Verification Script
REM Verifies all required wheel files are present for offline installation
REM ============================================================================

echo.
echo ============================================
echo iDRS Offline Package Verification
echo ============================================
echo.

cd offline_packages 2>nul
if errorlevel 1 (
    echo ERROR: offline_packages folder not found!
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

echo Checking for required packages...
echo.

set MISSING=0

REM Core Django packages
call :CheckFile "Django-5.1.5-py3-none-any.whl"
call :CheckFile "djangorestframework-3.15.2-py3-none-any.whl"
call :CheckFile "django_cors_headers-4.6.0-py3-none-any.whl"
call :CheckFile "asgiref-3.11.0-py3-none-any.whl"
call :CheckFile "sqlparse-0.5.5-py3-none-any.whl"

REM Data processing
call :CheckFile "numpy-2.4.1-cp313-cp313-win_amd64.whl"
call :CheckFile "pandas-2.2.3-cp313-cp313-win_amd64.whl"
call :CheckFile "python_dateutil-2.9.0.post0-py2.py3-none-any.whl"
call :CheckFile "pytz-2025.2-py2.py3-none-any.whl"
call :CheckFile "tzdata-2025.3-py2.py3-none-any.whl"
call :CheckFile "six-1.17.0-py2.py3-none-any.whl"

REM Optimization
call :CheckFile "ortools-9.15.6755-cp313-cp313-win_amd64.whl"
call :CheckFile "protobuf-6.33.4-cp310-abi3-win_amd64.whl"
call :CheckFile "absl_py-2.3.1-py3-none-any.whl"
call :CheckFile "immutabledict-4.2.2-py3-none-any.whl"
call :CheckFile "typing_extensions-4.15.0-py3-none-any.whl"

REM Excel and visualization
call :CheckFile "openpyxl-3.1.5-py2.py3-none-any.whl"
call :CheckFile "et_xmlfile-2.0.0-py3-none-any.whl"
call :CheckFile "plotly-5.24.1-py3-none-any.whl"
call :CheckFile "tenacity-9.1.2-py3-none-any.whl"
call :CheckFile "packaging-25.0-py3-none-any.whl"

REM Utilities
call :CheckFile "python_dotenv-1.0.1-py3-none-any.whl"
call :CheckFile "whitenoise-6.8.2-py3-none-any.whl"
call :CheckFile "ldap3-2.9.1-py2.py3-none-any.whl"
call :CheckFile "pyasn1-0.6.2-py3-none-any.whl"

REM Database
call :CheckFile "psycopg2_binary-2.9.11-cp313-cp313-win_amd64.whl"

REM Windows support
call :CheckFile "pywin32-311-cp313-cp313-win_amd64.whl"

echo.
echo ============================================

if %MISSING% EQU 0 (
    echo [SUCCESS] All required packages found!
    echo Total packages verified: 27
    echo.
    echo You can now proceed with offline installation:
    echo   "Install Windows\DEPLOY_VM.bat"
) else (
    echo [ERROR] %MISSING% package(s) missing!
    echo Please download missing packages before deployment.
)

echo ============================================
echo.

cd ..
pause
exit /b %MISSING%

:CheckFile
if exist "%~1" (
    echo [OK] %~1
) else (
    echo [MISSING] %~1
    set /a MISSING+=1
)
goto :eof
