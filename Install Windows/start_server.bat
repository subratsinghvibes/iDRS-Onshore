@echo off
REM ============================================
REM Start iDRS Server on Windows
REM ============================================

echo.
echo ====================================
echo Starting iDRS Server...
echo ====================================
echo.

REM Activate virtual environment
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo Virtual environment activated
) else (
    echo ERROR: Virtual environment not found!
    echo Please run setup_windows.bat first
    pause
    exit /b 1
)

REM Check if port is specified
if "%1"=="" (
    set PORT=8022
) else (
    set PORT=%1
)

echo.
echo Server will start on port %PORT%
echo Access the app at: http://localhost:%PORT%
echo Press Ctrl+C to stop the server
echo.

REM Start Django server on all interfaces (allows VM network access)
python manage.py runserver 0.0.0.0:%PORT%

pause
