@echo off
REM ============================================================================
REM Installation Test Script
REM Comprehensive verification of IDRS installation
REM ============================================================================

echo ========================================
echo IDRS Installation Test
echo ========================================
echo.

set ERRORS=0

REM Test 1: Python
echo [Test 1/7] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo FAILED: Python not found
    set /a ERRORS+=1
) else (
    echo PASSED: Python found
    python --version
)
echo.

REM Test 2: Virtual Environment
echo [Test 2/7] Checking virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo PASSED: Virtual environment exists
) else (
    echo FAILED: Virtual environment not found
    set /a ERRORS+=1
)
echo.

REM Test 3: Django
echo [Test 3/7] Checking Django installation...
call .venv\Scripts\activate.bat
python -c "import django; print('Django version:', django.get_version())" 2>nul
if errorlevel 1 (
    echo FAILED: Django not installed
    set /a ERRORS+=1
) else (
    echo PASSED: Django installed
)
echo.

REM Test 4: Video Processing Packages
echo [Test 4/7] Checking video processing packages...
python -c "import moviepy, imageio, PIL; print('Video packages OK')" 2>nul
if errorlevel 1 (
    echo FAILED: Video processing packages not installed
    set /a ERRORS+=1
) else (
    echo PASSED: Video processing packages installed
)
echo.

REM Test 5: FFmpeg
echo [Test 5/7] Checking FFmpeg installation...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo FAILED: FFmpeg not found
    echo WARNING: Video processing will not work!
    echo Install FFmpeg using: install_ffmpeg.bat
    set /a ERRORS+=1
) else (
    echo PASSED: FFmpeg found
    ffmpeg -version | findstr "ffmpeg version"
)
echo.

REM Test 6: Database
echo [Test 6/7] Checking database...
if exist "db.sqlite3" (
    echo PASSED: Database file exists
) else (
    echo WARNING: Database not initialized
    echo Run: setup_windows.bat
)
echo.

REM Test 7: Django Check
echo [Test 7/7] Running Django system check...
python manage.py check --deploy 2>nul
if errorlevel 1 (
    echo WARNING: Django check found issues
    echo This is normal for development setup
) else (
    echo PASSED: Django system check OK
)
echo.

REM Summary
echo ========================================
echo Test Summary
echo ========================================
echo.

if %ERRORS%==0 (
    echo ✅ All critical tests passed!
    echo.
    echo Installation is complete and ready to use.
    echo.
    echo Next steps:
    echo 1. Run: setup_windows.bat (if not done)
    echo 2. Run: start_server.bat
    echo 3. Access: http://localhost:8022
    echo.
) else (
    echo ❌ %ERRORS% test(s) failed!
    echo.
    echo Please fix the issues above before proceeding.
    echo.
    if %ERRORS% geq 3 (
        echo Critical errors detected. Run: install_offline_simple.bat
    )
    echo.
)

pause
