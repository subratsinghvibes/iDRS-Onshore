@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM iDRS - Load All Data into PostgreSQL
REM Run AFTER setup_postgres.bat (migrations must already be applied)
REM Run from the iDRS application root folder (where manage.py lives)
REM ============================================================================

echo.
echo ============================================================
echo  iDRS - Data Population Script
echo  Loads all fixture data into PostgreSQL
echo ============================================================
echo.
echo This script loads:
echo   - CompanyCode / LocationSpecFactors
echo   - IDT Norms (DailyDrillingRate, DrillingBenchmark, etc.)
echo   - MasterPersonnelInfo  ~24,000 rows  (may take 2-3 min)
echo   - AuthorizedUser       ~24,000 rows  (may take 1-2 min)
echo   - Schedule, WellBasket, VideoTutorial
echo.
echo Prerequisites:
echo   1. PostgreSQL is running and reachable
echo   2. Django migrations have been applied (run setup_postgres.bat first)
echo   3. The fixtures/ folder is present next to manage.py
echo.

if not exist "manage.py" (
    echo ERROR: manage.py not found.
    echo Run this script from the iDRS application root folder.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Run install_offline_simple.bat first.
    pause
    exit /b 1
)
if not exist "fixtures" (
    echo ERROR: fixtures\ folder not found.
    echo The fixtures folder must be in the same directory as manage.py.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
echo Virtual environment activated.
echo.

REM ── Check PostgreSQL TCP connectivity ─────────────────────────────────────
echo Checking PostgreSQL connection...
python -c "import socket; s=socket.create_connection(open('.env').read().split('//')[1].split(':')[0].strip() if 'DATABASE_URL' in open('.env').read() else '10.212.64.16', 5432, timeout=5); s.close()" >nul 2>&1
REM Simple fallback check — if psycopg2 test fails we warn but continue
python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','drilling_scheduler.settings'); django.setup(); from django.db import connection; connection.ensure_connection()" >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Could not connect to PostgreSQL.
    echo Make sure PostgreSQL is running and .env DATABASE_URL is correct.
    echo.
    set /p CONT="Continue anyway? (Y/N): "
    if /i not "!CONT!"=="Y" exit /b 1
)
echo   Connection OK.
echo.

REM ── Menu ──────────────────────────────────────────────────────────────────
echo Choose what to load:
echo.
echo   1) All data incl. MasterPersonnelInfo + AuthorizedUser  (recommended, ~5 min)
echo   2) All data EXCEPT large tables  (fast, ~30 sec)
echo   3) Reference + IDT Norms only   (fastest, ~10 sec)
echo   4) Large tables only  (MPI + AuthorizedUser — after norms already loaded)
echo.
set /p LOAD_CHOICE="Enter choice (1/2/3/4): "

if "!LOAD_CHOICE!"=="1" goto :load_all
if "!LOAD_CHOICE!"=="2" goto :load_no_large
if "!LOAD_CHOICE!"=="3" goto :load_norms_only
if "!LOAD_CHOICE!"=="4" goto :load_large_only
echo Invalid choice. Exiting.
pause
exit /b 1

:load_all
echo.
echo [LOADING] All fixtures (this may take 5-7 minutes for the large tables)...
echo.
python manage.py load_all_data
goto :check_result

:load_no_large
echo.
echo [LOADING] All fixtures except MasterPersonnelInfo + AuthorizedUser...
echo.
python manage.py load_all_data --skip-large
goto :check_result

:load_norms_only
echo.
echo [LOADING] Reference data + IDT Norms only...
echo.
python manage.py load_all_data --only reference
python manage.py load_all_data --only norms
python manage.py load_all_data --only misc
goto :check_result

:load_large_only
echo.
echo [LOADING] Large tables only (MasterPersonnelInfo + AuthorizedUser)...
echo.
python manage.py load_all_data --only large
goto :check_result

:check_result
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  One or more fixtures had errors.  See output above.
    echo
    echo  Most common fix: if you see "duplicate key" errors, the data
    echo  already exists in the DB.  That is safe to ignore.
    echo  Re-run with --skip-large if a large file timed out.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Data load complete!
echo ============================================================
echo.
echo  Next steps:
echo    1. Create admin user:
echo       python manage.py createsuperuser
echo.
echo    2. Start the server:
echo       "Install Windows\start_server.bat"
echo.
echo    3. Access the app:
echo       http://10.212.64.16:8022
echo       http://localhost:8022
echo.
echo    4. Django Admin for VideoTutorial re-uploads:
echo       http://10.212.64.16:8022/admin
echo.
pause
exit /b 0
