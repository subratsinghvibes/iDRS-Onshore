@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM iDRS - Apply Database Migrations
REM Stops the server, applies pending migrations, then restarts the server.
REM Run from the iDRS application root folder (where manage.py lives).
REM
REM Usage:
REM   apply_migrations.bat              - apply all pending migrations
REM   apply_migrations.bat scheduler    - apply a specific app only
REM   apply_migrations.bat scheduler 0061  - migrate to a specific migration
REM ============================================================================

title iDRS - Apply Migrations

echo.
echo ============================================================
echo  iDRS - Apply Database Migrations
echo ============================================================
echo.

REM Must be run from the project root (where manage.py lives)
if not exist "manage.py" (
    echo ERROR: manage.py not found.
    echo Please run this script from the iDRS project root folder,
    echo e.g.:  cd C:\iDRS  then  apply_migrations.bat
    pause
    exit /b 1
)

REM Virtual environment check
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at .venv\Scripts\activate.bat
    echo Please run install_offline_simple.bat or setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Verify Django
python -c "import django" 2>nul
if errorlevel 1 (
    echo ERROR: Django is not installed in the virtual environment.
    echo Please run install_offline_simple.bat first.
    pause
    exit /b 1
)

REM ============================================================
REM STEP 1: Stop the iDRS server (free the database lock)
REM ============================================================
echo [1/4] Stopping iDRS server (freeing database)...
echo.

for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8022 "') do (
    taskkill /F /PID %%p >nul 2>&1
)
taskkill /F /FI "WINDOWTITLE eq iDRS*" >nul 2>&1
timeout /t 2 /nobreak >nul

echo   Server stopped (or was not running).
echo.

REM ============================================================
REM STEP 2: Check whether any migrations need applying
REM   "migrate --check" exits with code 1 if there are unapplied
REM   migrations, 0 if the database is already up to date.
REM   It does NOT parse text so it is immune to warning messages.
REM ============================================================
echo [2/4] Checking migration status...
echo.

python manage.py migrate --check >nul 2>&1
if not errorlevel 1 (
    echo   Database is already up to date. No migrations to apply.
    echo.
    goto :already_up_to_date
)

echo   Pending migrations detected. Proceeding to apply...
echo.

REM ============================================================
REM STEP 3: Apply migrations
REM ============================================================
set "MIGRATE_ARGS="
if not "%~1"=="" (
    set "MIGRATE_ARGS=%~1"
    if not "%~2"=="" set "MIGRATE_ARGS=%~1 %~2"
)

echo [3/4] Applying migrations: python manage.py migrate !MIGRATE_ARGS!
echo.
python manage.py migrate !MIGRATE_ARGS!

REM ============================================================
REM STEP 4: Verify with --check (exit 0 = success, 1 = still pending)
REM ============================================================
echo.
echo [4/4] Verifying...
echo.

python manage.py migrate --check >nul 2>&1
if errorlevel 1 (
    echo ============================================================
    echo  ERROR: Migrations still pending after running migrate!
    echo ============================================================
    echo.
    echo This means the migration FILES are missing from the deployment.
    echo Copy the full scheduler\migrations\ folder from the source
    echo machine and run this script again.
    echo.
    echo To diagnose, run:
    echo   python manage.py showmigrations
    echo   python manage.py migrate --verbosity 2
    echo.
    pause
    exit /b 1
)

echo   All migrations applied successfully.

REM Warn (not error) if models have uncommitted changes
python manage.py makemigrations --check >nul 2>&1
if errorlevel 1 (
    echo.
    echo   NOTE: models.py has changes not yet in a migration file.
    echo   This is a developer task - the app will still run normally.
    echo   On the source machine run: python manage.py makemigrations
    echo   then redeploy the new migration file.
)
goto :done

:already_up_to_date
echo [3/4] Nothing to apply - skipping migrate.
echo [4/4] Verification complete - all migrations up to date.

REM Still warn about model drift
python manage.py makemigrations --check >nul 2>&1
if errorlevel 1 (
    echo.
    echo   NOTE: models.py has changes not yet in a migration file.
    echo   The app will still run normally but some new fields may be
    echo   missing until migrations are generated and deployed.
)

:done
echo.
echo ============================================================
echo  Migration complete.
echo ============================================================
echo.

REM ============================================================
REM Restart the server
REM ============================================================
set /p RESTART="  Restart the iDRS server now? (Y/N, default Y): "
if /i "!RESTART!"=="N" goto :no_restart

echo.
echo  Starting iDRS server on port 8022...
echo  (Close the new window or press Ctrl+C there to stop the server)
echo.
start "iDRS - Interactive Drilling Rig Scheduler" cmd /k "call .venv\Scripts\activate.bat && python manage.py runserver 0.0.0.0:8022"
echo  Server started in a new window.
goto :end

:no_restart
echo  Server not restarted. Run run_server.bat when ready.

:end
echo.
pause
exit /b 0
pause
exit /b 0
