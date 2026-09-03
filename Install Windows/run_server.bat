@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM iDRS - Run Server
REM Sets the terminal window title and starts Django on 0.0.0.0:8022
REM Run from the iDRS application root folder (where manage.py lives)
REM ============================================================================

title iDRS - Interactive Drilling Rig Scheduler

if not exist "manage.py" (
    echo ERROR: manage.py not found. Run from the iDRS project root.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Port: first argument or default 8022
set "PORT=8022"
if not "%~1"=="" set "PORT=%~1"

REM Detect local IPv4 address (first non-loopback)
set "LOCAL_IP=this-machine"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    set "LOCAL_IP=%%a"
    goto :got_ip
)
:got_ip
set "LOCAL_IP=!LOCAL_IP: =!"

echo.
echo ============================================================
echo  iDRS - Interactive Drilling Rig Scheduler
echo  Server starting on port !PORT!
echo ============================================================
echo.
echo  Local  : http://localhost:!PORT!
echo  Network: http://!LOCAL_IP!:!PORT!
echo  Admin  : http://!LOCAL_IP!:!PORT!/admin
echo.
echo  Press Ctrl+C to stop the server.
echo ============================================================
echo.

python manage.py runserver 0.0.0.0:!PORT!

pause
