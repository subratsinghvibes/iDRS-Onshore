@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM iDRS - PostgreSQL Database Setup Script
REM Target VM: 10.212.64.16   Python 3.13.9
REM Run from the iDRS application root folder (where manage.py lives)
REM ============================================================================
REM IMPORTANT: This script uses ONLY flat if/goto - no labels inside () blocks.
REM            This is required for correct Windows batch parsing.
REM ============================================================================

echo.
echo ============================================================
echo  iDRS - PostgreSQL Database Setup
echo  Target VM: 10.212.64.16  (localhost / same machine)
echo ============================================================
echo.
echo This script will:
echo   1. Check prerequisites  (Python venv psql)
echo   2. Collect connection details
echo   3. Create PostgreSQL database + user
echo   4. Write .env configuration file
echo   5. Install psycopg2 and dj-database-url from offline packages
echo   6. Run Django migrations (creates all tables)
echo   7. Collect static files
echo   8. Optionally create a Django admin superuser
echo.
echo Press any key to start or Ctrl+C to cancel...
pause >nul
echo.

REM ============================================================================
REM STEP 0 - Prerequisites  (flat gotos - no nested parentheses)
REM ============================================================================
echo [STEP 0/7] Checking prerequisites...
echo.

if not exist "manage.py" goto :err_no_managepy
if not exist ".venv\Scripts\activate.bat" goto :err_no_venv

call .venv\Scripts\activate.bat
echo Virtual environment activated.

python --version >nul 2>&1
if errorlevel 1 goto :err_no_python
echo Python OK:
python --version
echo.

REM ============================================================================
REM STEP 0b - Locate psql  (flat if chain - NO labels inside parenthesised blocks)
REM ============================================================================
echo Locating psql...
set "PSQL_CMD="

where psql >nul 2>&1
if not errorlevel 1 set "PSQL_CMD=psql"
if not "!PSQL_CMD!"=="" echo   psql found in PATH.
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\17\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\17\bin\psql.exe"
if not "!PSQL_CMD!"=="" echo   psql found: PostgreSQL 17
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\16\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\16\bin\psql.exe"
if not "!PSQL_CMD!"=="" echo   psql found: PostgreSQL 16
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\15\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\15\bin\psql.exe"
if not "!PSQL_CMD!"=="" echo   psql found: PostgreSQL 15
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\14\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\14\bin\psql.exe"
if not "!PSQL_CMD!"=="" echo   psql found: PostgreSQL 14
if not "!PSQL_CMD!"=="" goto :psql_found

REM psql not found anywhere
echo.
echo   WARNING: psql.exe not found in PATH or standard PostgreSQL
echo   install locations (versions 14-17).
echo.
echo   Options:
echo     A) Add PostgreSQL bin to PATH and re-run this script.
echo        Example:  set PATH=%%PATH%%;C:\Program Files\PostgreSQL\17\bin
echo.
echo     B) Create DB manually in pgAdmin then re-run and skip below.
echo.
set /p SKIP_CREATE="Skip DB creation (DB+user already exist)? (Y=skip / N=exit): "
if /i "!SKIP_CREATE!"=="Y" goto :psql_skip
echo.
echo Exiting. Please configure PostgreSQL and re-run.
pause
exit /b 1

:psql_skip
set "PSQL_CMD=SKIP"

:psql_found
echo.

REM ============================================================================
REM STEP 1 - Connection details
REM ============================================================================
echo [STEP 1/7] PostgreSQL connection configuration
echo.
echo Press ENTER on each line to accept the default shown in brackets.
echo.

set "PG_HOST=10.212.64.16"
set /p PG_HOST_INPUT="  Host     [10.212.64.16]: "
if not "!PG_HOST_INPUT!"=="" set "PG_HOST=!PG_HOST_INPUT!"

set "PG_PORT=5432"
set /p PG_PORT_INPUT="  Port     [5432]: "
if not "!PG_PORT_INPUT!"=="" set "PG_PORT=!PG_PORT_INPUT!"

set "PG_DBNAME=idrs_db"
set /p PG_DBNAME_INPUT="  Database [idrs_db]: "
if not "!PG_DBNAME_INPUT!"=="" set "PG_DBNAME=!PG_DBNAME_INPUT!"

set "PG_USER=idrs_user"
set /p PG_USER_INPUT="  App user [idrs_user]: "
if not "!PG_USER_INPUT!"=="" set "PG_USER=!PG_USER_INPUT!"

:ask_password
set "PG_PASSWORD="
set /p PG_PASSWORD="  Password (required no default): "
if "!PG_PASSWORD!"=="" echo   Password cannot be empty. & goto :ask_password

echo.
echo  Summary:
echo    Host: !PG_HOST!   Port: !PG_PORT!
echo    DB  : !PG_DBNAME!
echo    User: !PG_USER!
echo    Pass: (hidden)
echo.

REM ============================================================================
REM STEP 2 - Create DB and user  (flat: no multi-line error blocks)
REM ============================================================================
echo [STEP 2/7] Creating PostgreSQL database and user...
echo.

if "!PSQL_CMD!"=="SKIP" goto :step2_skip

set "PG_SUPERUSER=postgres"
set /p PG_SU_INPUT="  Superuser for DB creation [postgres]: "
if not "!PG_SU_INPUT!"=="" set "PG_SUPERUSER=!PG_SU_INPUT!"

echo.
echo   You will be prompted for the !PG_SUPERUSER! password.
echo.

REM Write role SQL to a temp file (DO $$ blocks break with inline -c)
set "SETUP_SQL=%TEMP%\idrs_pg_%RANDOM%.sql"
(
echo DO ^$^$
echo BEGIN
echo   IF NOT EXISTS ^(SELECT FROM pg_catalog.pg_roles WHERE rolname = '!PG_USER!'^) THEN
echo     CREATE ROLE "!PG_USER!" WITH LOGIN PASSWORD '!PG_PASSWORD!';
echo     RAISE NOTICE 'Created role !PG_USER!';
echo   ELSE
echo     ALTER ROLE "!PG_USER!" WITH PASSWORD '!PG_PASSWORD!';
echo     RAISE NOTICE 'Updated password for !PG_USER!';
echo   END IF;
echo END
echo ^$^$;
) > "!SETUP_SQL!"

"!PSQL_CMD!" -h !PG_HOST! -p !PG_PORT! -U !PG_SUPERUSER! -f "!SETUP_SQL!"
if errorlevel 1 goto :err_psql_user
del "!SETUP_SQL!" 2>nul
echo   Role "!PG_USER!" ready.

"!PSQL_CMD!" -h !PG_HOST! -p !PG_PORT! -U !PG_SUPERUSER! -tc "SELECT 1 FROM pg_database WHERE datname='!PG_DBNAME!'" 2>nul | findstr /C:"1" >nul 2>&1
if not errorlevel 1 goto :db_exists

echo   Creating database !PG_DBNAME!...
"!PSQL_CMD!" -h !PG_HOST! -p !PG_PORT! -U !PG_SUPERUSER! -c "CREATE DATABASE \"!PG_DBNAME!\" OWNER \"!PG_USER!\";"
if errorlevel 1 goto :err_psql_db
echo   Database "!PG_DBNAME!" created.
goto :db_grant

:db_exists
echo   Database "!PG_DBNAME!" already exists.

:db_grant
"!PSQL_CMD!" -h !PG_HOST! -p !PG_PORT! -U !PG_SUPERUSER! -c "GRANT ALL PRIVILEGES ON DATABASE \"!PG_DBNAME!\" TO \"!PG_USER!\";"
if errorlevel 1 echo   WARNING: GRANT failed - see output above.
echo   Database step complete.
echo.
goto :step3

:step2_skip
echo   Skipping DB creation as requested.
echo.

REM ============================================================================
REM STEP 3 - Write .env
REM ============================================================================
:step3
echo [STEP 3/7] Writing .env configuration...
echo.

if exist ".env" copy ".env" ".env.backup" >nul & echo   Existing .env backed up to .env.backup

set "DATABASE_URL=postgresql://!PG_USER!:!PG_PASSWORD!@!PG_HOST!:!PG_PORT!/!PG_DBNAME!"

(
echo # iDRS Environment Configuration - generated by setup_postgres.bat
echo # KEEP THIS FILE SECURE - contains database credentials
echo.
echo SECRET_KEY=
echo DEBUG=False
echo USE_HTTPS=False
echo.
echo ALLOWED_HOSTS=localhost,127.0.0.1,10.212.64.16,0.0.0.0
echo.
echo # PostgreSQL on 10.212.64.16
echo DATABASE_URL=!DATABASE_URL!
echo.
echo LDAP_SERVER=ldap://10.205.48.230:389
echo LDAP_BASE_DN=DC=ONGC,DC=ONGCGroup,DC=co,DC=in
echo LDAP_USE_SSL=False
echo LDAP_VERIFY_SSL=False
echo LDAP_DOMAIN=ongcgroup.co.in
) > ".env"

if errorlevel 1 goto :err_env
echo   .env written.
echo   (SECRET_KEY blank - Django auto-generates and persists it.)
echo.

REM ============================================================================
REM STEP 4 - Python drivers
REM ============================================================================
echo [STEP 4/7] Installing Python PostgreSQL drivers from offline packages...
echo.

set "PIP_NO_INDEX=1"
set "PIP_RETRIES=0"
set "PIP_TIMEOUT=1"

python -m pip install --no-index --find-links=offline_packages psycopg2-binary
if errorlevel 1 goto :err_pip_psycopg2

python -m pip install --no-index --find-links=offline_packages dj-database-url
if errorlevel 1 goto :err_pip_dj

echo   Both drivers installed.
echo.

REM ============================================================================
REM STEP 4b - Test PostgreSQL TCP connectivity before migrations
REM ============================================================================
echo [STEP 4b/7] Testing TCP connection to PostgreSQL at !PG_HOST!:!PG_PORT!...
echo.

python -c "import socket; s=socket.create_connection(('!PG_HOST!',int('!PG_PORT!')),timeout=5); s.close()" >nul 2>&1
if errorlevel 1 goto :fix_pg_tcp
echo   TCP connection OK - PostgreSQL is reachable.
echo.
goto :step5_migrate

REM ============================================================================
REM FIX - PostgreSQL not accepting TCP/IP connections
REM ============================================================================
:fix_pg_tcp
echo ============================================================
echo  PostgreSQL port !PG_PORT! is NOT reachable at !PG_HOST!
echo  Error: Connection refused - TCP/IP is disabled in PostgreSQL
echo  or Windows Firewall is blocking port !PG_PORT!.
echo ============================================================
echo.
echo  Auto-fixing PostgreSQL configuration...
echo  (Requires Administrator privileges - ensure this window is elevated)
echo.

REM --- Detect PostgreSQL data directory from standard install locations ---
set "PG_DATA="
set "PG_SVC_NAME="

if exist "C:\Program Files\PostgreSQL\17\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\17\data"
if exist "C:\Program Files\PostgreSQL\17\data\postgresql.conf" set "PG_SVC_NAME=postgresql-x64-17"

if "!PG_DATA!"=="" if exist "C:\Program Files\PostgreSQL\16\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\16\data"
if "!PG_SVC_NAME!"=="" if exist "C:\Program Files\PostgreSQL\16\data\postgresql.conf" set "PG_SVC_NAME=postgresql-x64-16"

if "!PG_DATA!"=="" if exist "C:\Program Files\PostgreSQL\15\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\15\data"
if "!PG_SVC_NAME!"=="" if exist "C:\Program Files\PostgreSQL\15\data\postgresql.conf" set "PG_SVC_NAME=postgresql-x64-15"

if "!PG_DATA!"=="" if exist "C:\Program Files\PostgreSQL\14\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\14\data"
if "!PG_SVC_NAME!"=="" if exist "C:\Program Files\PostgreSQL\14\data\postgresql.conf" set "PG_SVC_NAME=postgresql-x64-14"

if "!PG_DATA!"=="" goto :fix_pg_manual

echo   Found PostgreSQL data dir: !PG_DATA!
echo   Service name            : !PG_SVC_NAME!
echo.

REM --- Step A: Patch postgresql.conf (append overrides last value read) ---
echo   [Fix A] Patching postgresql.conf: listen_addresses = '*' ...
echo. >> "!PG_DATA!\postgresql.conf"
echo # iDRS auto-fix: enable TCP/IP on all interfaces >> "!PG_DATA!\postgresql.conf"
echo listen_addresses = '*' >> "!PG_DATA!\postgresql.conf"
echo port = !PG_PORT! >> "!PG_DATA!\postgresql.conf"
if errorlevel 1 echo   WARNING: Could not write to postgresql.conf - try running as Administrator
if not errorlevel 1 echo   postgresql.conf updated.
echo.

REM --- Step B: Append host rule to pg_hba.conf ---
echo   [Fix B] Updating pg_hba.conf: allowing all TCP connections (md5)...
echo. >> "!PG_DATA!\pg_hba.conf"
echo # iDRS auto-fix: allow all TCP connections >> "!PG_DATA!\pg_hba.conf"
echo host    all             all             0.0.0.0/0               md5 >> "!PG_DATA!\pg_hba.conf"
if errorlevel 1 echo   WARNING: Could not write to pg_hba.conf
if not errorlevel 1 echo   pg_hba.conf updated.
echo.

REM --- Step C: Open Windows Firewall ---
echo   [Fix C] Opening Windows Firewall for TCP port !PG_PORT!...
netsh advfirewall firewall delete rule name="PostgreSQL iDRS" >nul 2>&1
netsh advfirewall firewall add rule name="PostgreSQL iDRS" dir=in action=allow protocol=TCP localport=!PG_PORT! >nul 2>&1
if errorlevel 1 echo   WARNING: Could not add firewall rule (run as Administrator)
if not errorlevel 1 echo   Firewall rule added.
echo.

REM --- Step D: Restart PostgreSQL service ---
echo   [Fix D] Restarting PostgreSQL service: !PG_SVC_NAME!...
net stop "!PG_SVC_NAME!" >nul 2>&1
net start "!PG_SVC_NAME!"
if errorlevel 1 goto :err_pg_restart
echo   Service restarted.
echo.
echo   Waiting 5 seconds for PostgreSQL to come up...
timeout /t 5 /nobreak >nul

REM --- Re-test TCP connection ---
echo   Re-testing TCP connection to !PG_HOST!:!PG_PORT!...
python -c "import socket; s=socket.create_connection(('!PG_HOST!',int('!PG_PORT!')),timeout=8); s.close()" >nul 2>&1
if errorlevel 1 goto :err_pg_tcp_retry
echo   PostgreSQL TCP connection now working!
echo.
goto :step5_migrate

:fix_pg_manual
echo ============================================================
echo  Could not auto-detect the PostgreSQL data directory.
echo  Please fix PostgreSQL TCP/IP manually:
echo.
echo  STEP 1 - Find config file location (run in psql as postgres):
echo    SHOW config_file;
echo    SHOW hba_file;
echo.
echo  STEP 2 - Edit postgresql.conf, add/change:
echo    listen_addresses = '*'
echo    port = !PG_PORT!
echo.
echo  STEP 3 - Edit pg_hba.conf, add at the bottom:
echo    host  all  all  0.0.0.0/0  md5
echo.
echo  STEP 4 - Open Windows Firewall (run as Admin):
echo    netsh advfirewall firewall add rule name="PostgreSQL" ^
echo      dir=in action=allow protocol=TCP localport=!PG_PORT!
echo.
echo  STEP 5 - Restart PostgreSQL service:
echo    net stop postgresql-x64-17
echo    net start postgresql-x64-17
echo.
echo  STEP 6 - Re-run this script.
echo ============================================================
pause
exit /b 1

:err_pg_restart
echo.
echo ============================================================
echo  ERROR: Could not restart PostgreSQL service "!PG_SVC_NAME!"
echo.
echo  Try manually:
echo    1. Open services.msc
echo    2. Find "!PG_SVC_NAME!" (or your PostgreSQL version)
echo    3. Right-click -> Restart
echo    4. Re-run this script
echo ============================================================
pause
exit /b 1

:err_pg_tcp_retry
echo.
echo ============================================================
echo  PostgreSQL still not reachable at !PG_HOST!:!PG_PORT! after auto-fix.
echo.
echo  Manual checks:
echo    1. Open services.msc - confirm PostgreSQL service is running
echo    2. Check postgresql.conf contains: listen_addresses = '*'
echo       (C:\Program Files\PostgreSQL\17\data\postgresql.conf)
echo    3. Check pg_hba.conf has: host all all 0.0.0.0/0 md5
echo    4. Try: netstat -an | findstr :!PG_PORT!
echo       (should show 0.0.0.0:!PG_PORT! LISTENING)
echo    5. Test: psql -h !PG_HOST! -p !PG_PORT! -U !PG_USER! -d !PG_DBNAME!
echo.
echo  Re-run this script after fixing.
echo ============================================================
pause
exit /b 1

REM ============================================================================
REM STEP 5 - Migrations
REM ============================================================================
:step5_migrate
echo [STEP 5/7] Running Django migrations...
echo.

python manage.py migrate --verbosity=1
if errorlevel 1 goto :err_migrate
echo   Migrations complete.
echo.

REM ============================================================================
REM STEP 6 - Static files
REM ============================================================================
echo [STEP 6/7] Collecting static files...
echo.

python manage.py collectstatic --noinput
if errorlevel 1 echo   WARNING: collectstatic had issues - CSS/JS may not load. See above.
if not errorlevel 1 echo   Static files collected.
echo.

REM ============================================================================
REM STEP 7 - Superuser
REM ============================================================================
echo [STEP 7/7] Create Django admin superuser
echo.
set /p CREATE_SU="Create a Django admin superuser now? (Y/N): "
if /i not "!CREATE_SU!"=="Y" goto :done

python manage.py createsuperuser
if errorlevel 1 echo   NOTE: If username already exists that is normal.
if not errorlevel 1 echo   Superuser created.
echo.

REM ============================================================================
REM DONE
REM ============================================================================
:done
echo.
echo ============================================================
echo  PostgreSQL Setup Complete!
echo ============================================================
echo.
echo  Database : !PG_DBNAME! on !PG_HOST!:!PG_PORT!
echo  User     : !PG_USER!
echo  Config   : .env  (DATABASE_URL configured)
echo.
echo  Start the server:
echo    "Install Windows\start_server.bat"
echo.
echo  Access the app:
echo    http://10.212.64.16:8022
echo    http://localhost:8022
echo.
echo  Django admin: http://10.212.64.16:8022/admin
echo.
pause
exit /b 0

REM ============================================================================
REM ERROR LABELS  (ALL outside any parentheses block)
REM ============================================================================

:err_no_managepy
echo.
echo ============================================================
echo  ERROR: manage.py not found in current directory.
echo.
echo  Run from the iDRS application root folder.
echo  Example:
echo    cd C:\iDRS
echo    "Install Windows\setup_postgres.bat"
echo ============================================================
pause
exit /b 1

:err_no_venv
echo.
echo ============================================================
echo  ERROR: Virtual environment not found.
echo    Expected: .venv\Scripts\activate.bat
echo.
echo  Run install_offline_simple.bat first.
echo ============================================================
pause
exit /b 1

:err_no_python
echo.
echo ============================================================
echo  ERROR: Python not available in the virtual environment.
echo.
echo  Delete .venv and run install_offline_simple.bat again.
echo ============================================================
pause
exit /b 1

:err_psql_user
del "!SETUP_SQL!" 2>nul
echo.
echo ============================================================
echo  ERROR: Could not create/update PostgreSQL role "!PG_USER!"
echo.
echo  Possible causes:
echo    - Wrong superuser (!PG_SUPERUSER!) password
echo    - PostgreSQL not running on !PG_HOST!:!PG_PORT!
echo    - pg_hba.conf authentication issue
echo    - Firewall blocking port !PG_PORT!
echo.
echo  Test: psql -h !PG_HOST! -p !PG_PORT! -U !PG_SUPERUSER!
echo ============================================================
pause
exit /b 1

:err_psql_db
echo.
echo ============================================================
echo  ERROR: Could not create database "!PG_DBNAME!"
echo.
echo  Create it manually:
echo    CREATE DATABASE !PG_DBNAME! OWNER !PG_USER!;
echo    GRANT ALL PRIVILEGES ON DATABASE !PG_DBNAME! TO !PG_USER!;
echo ============================================================
pause
exit /b 1

:err_env
echo.
echo ============================================================
echo  ERROR: Failed to write .env file.
echo  Check write permissions on the application folder.
echo ============================================================
pause
exit /b 1

:err_pip_psycopg2
echo.
echo ============================================================
echo  ERROR: psycopg2-binary installation failed.
echo.
echo  Expected wheel in offline_packages\:
echo    psycopg2_binary-2.9.11-cp313-cp313-win_amd64.whl
echo ============================================================
pause
exit /b 1

:err_pip_dj
echo.
echo ============================================================
echo  ERROR: dj-database-url installation failed.
echo.
echo  Expected wheel in offline_packages\:
echo    dj_database_url-3.1.2-py3-none-any.whl
echo ============================================================
pause
exit /b 1

:err_migrate
echo.
echo ============================================================
echo  ERROR: Django migrations failed.
echo.
echo  Full Django traceback shown above.
echo.
echo  Common causes:
echo    - Cannot connect to PostgreSQL (wrong host/port/password)
echo    - Database "!PG_DBNAME!" does not exist
echo    - User "!PG_USER!" lacks CREATE TABLE privileges
echo.
echo  DATABASE_URL: !DATABASE_URL!
echo.
echo  Test: psql -h !PG_HOST! -p !PG_PORT! -U !PG_USER! -d !PG_DBNAME!
echo ============================================================
pause
exit /b 1
