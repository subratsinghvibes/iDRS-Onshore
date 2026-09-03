@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM iDRS - Reset Admin / Superuser Password
REM Run from the iDRS application root folder (where manage.py lives)
REM ============================================================================

title iDRS - Reset Admin Password

REM ---- Pre-flight checks -----------------------------------------------------
if not exist "manage.py" (
    echo.
    echo ERROR: manage.py not found.
    echo        Run this script from the iDRS project root folder.
    echo        Example:  cd "C:\...\8022 iDRS v11.4"
    echo        Then run: "Install Windows\reset_admin_password.bat"
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo ERROR: Virtual environment not found.
    echo        Run setup.bat first, or check that the .venv folder exists.
    pause
    exit /b 1
)

if not exist "reset_admin_password.py" (
    echo.
    echo ERROR: reset_admin_password.py not found in the project root.
    echo        Make sure the file was copied alongside manage.py.
    pause
    exit /b 1
)

REM ---- Activate venv and run Python helper -----------------------------------
call .venv\Scripts\activate.bat

python reset_admin_password.py
set "EXIT_CODE=!ERRORLEVEL!"

echo.
pause
exit /b !EXIT_CODE!
