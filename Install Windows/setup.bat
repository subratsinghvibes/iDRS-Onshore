@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM iDRS - Complete Setup Script  (PostgreSQL + LDAP)
REM Target VM: 10.212.64.16   Python 3.13.9
REM Run from the iDRS application root folder (where manage.py lives)
REM ============================================================================

title iDRS - Setup

echo.
echo ============================================================
echo  iDRS - Interactive Drilling Rig Scheduler
echo  Complete Setup  (PostgreSQL + LDAP)
echo ============================================================
echo.
echo  This script will:
echo   [1] Create Python virtual environment
echo   [2] Install all packages from offline_packages
echo   [3] Setup PostgreSQL  (create DB, user, .env)
echo   [4] Run Django migrations
echo   [5] Collect static files
echo   [6] Load fixture data  (IDT Norms, AuthorizedUser, etc.)
echo   [7] Create Django admin superuser
echo.
echo Press any key to start or Ctrl+C to cancel...
pause >nul
echo.

if not exist "manage.py" goto :err_no_managepy

REM ============================================================================
REM [1] PYTHON + VIRTUAL ENVIRONMENT
REM ============================================================================
echo [1/7] Setting up Python virtual environment...
echo.

python --version >nul 2>&1
if errorlevel 1 goto :err_no_python

echo   Python found:
python --version

if exist ".venv" goto :venv_exists
echo   Creating virtual environment...
python -m venv .venv
if errorlevel 1 goto :err_venv_create
echo   Virtual environment created.
goto :venv_activate

:venv_exists
echo   Virtual environment already exists.

:venv_activate
call .venv\Scripts\activate.bat
echo   Virtual environment activated.
echo.

REM ============================================================================
REM [2] INSTALL ALL PACKAGES FROM OFFLINE_PACKAGES
REM ============================================================================
echo [2/7] Installing all packages from offline_packages...
echo.

if not exist "offline_packages" goto :err_no_packages

set PIP_NO_INDEX=1
set PIP_RETRIES=0
set PIP_TIMEOUT=1

echo   [2a] Core: Django, DRF, CORS...
python -m pip install --no-index --find-links=offline_packages --quiet Django djangorestframework django-cors-headers asgiref sqlparse typing-extensions 2>nul
if errorlevel 1 echo     WARNING: Some core packages had issues

echo   [2b] PostgreSQL drivers...
python -m pip install --no-index --find-links=offline_packages --quiet psycopg2-binary dj-database-url python-dotenv 2>nul
if errorlevel 1 echo     WARNING: PostgreSQL driver issues

echo   [2c] Data processing: numpy, pandas, OR-Tools...
python -m pip install --no-index --find-links=offline_packages --quiet six python-dateutil pytz tzdata numpy pandas protobuf absl-py immutabledict ortools 2>nul
if errorlevel 1 echo     WARNING: Data processing packages had issues

echo   [2d] Excel, charts, images...
python -m pip install --no-index --find-links=offline_packages --quiet et-xmlfile openpyxl packaging tenacity plotly Pillow 2>nul
if errorlevel 1 echo     WARNING: Visualization packages had issues

echo   [2e] LDAP authentication...
python -m pip install --no-index --find-links=offline_packages --quiet ldap3 pyasn1 2>nul
if errorlevel 1 echo     WARNING: LDAP packages had issues

echo   [2f] Static files + Windows + video processing...
python -m pip install --no-index --find-links=offline_packages --quiet whitenoise pywin32 decorator imageio imageio-ffmpeg moviepy proglog tqdm colorama 2>nul
if errorlevel 1 echo     WARNING: Some optional packages had issues

echo   Configuring pywin32...
python .venv\Scripts\pywin32_postinstall.py -install >nul 2>&1
echo.

REM Verify critical packages
echo   Verifying critical packages...
python -c "import django; print(f'    Django {django.VERSION[0]}.{django.VERSION[1]}.{django.VERSION[2]}')" 2>nul
if errorlevel 1 goto :err_django_missing
python -c "import psycopg2; print(f'    psycopg2 {psycopg2.__version__}')" 2>nul
if errorlevel 1 echo     WARNING: psycopg2 not installed - PostgreSQL won't work
python -c "import ldap3; print(f'    ldap3 {ldap3.__version__}')" 2>nul
if errorlevel 1 echo     WARNING: ldap3 not installed - LDAP login won't work
python -c "import ortools; print('    OR-Tools OK')" 2>nul
if errorlevel 1 echo     WARNING: OR-Tools not installed - scheduler optimization won't work
echo   Package installation complete.
echo.

REM ============================================================================
REM [3] POSTGRESQL SETUP
REM ============================================================================
echo [3/7] PostgreSQL configuration
echo.
echo Press ENTER to accept the default shown in [brackets].
echo.

REM --- 3a: Locate psql ---
set "PSQL_CMD="

where psql >nul 2>&1
if not errorlevel 1 set "PSQL_CMD=psql"
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\17\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\17\bin\psql.exe"
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\16\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\16\bin\psql.exe"
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\15\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\15\bin\psql.exe"
if not "!PSQL_CMD!"=="" goto :psql_found

if exist "C:\Program Files\PostgreSQL\14\bin\psql.exe" set "PSQL_CMD=C:\Program Files\PostgreSQL\14\bin\psql.exe"
if not "!PSQL_CMD!"=="" goto :psql_found

echo   psql.exe not found. DB creation will be skipped.
echo   Create the database and user manually in pgAdmin before continuing.
echo.
set /p SKIP_PG="DB and user already exist? (Y=continue / N=exit): "
if /i not "!SKIP_PG!"=="Y" goto :err_no_psql
set "PSQL_CMD=SKIP"
goto :pg_connection_details

:psql_found
echo   psql found.

:pg_connection_details
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
set /p PG_PASSWORD="  Password (required): "
if "!PG_PASSWORD!"=="" echo   Password cannot be empty. & goto :ask_password

echo.

REM --- 3b: Create DB + user (if psql available) ---
if "!PSQL_CMD!"=="SKIP" goto :write_env

set "PG_SUPERUSER=postgres"
set /p PG_SU_INPUT="  PG superuser for DB creation [postgres]: "
if not "!PG_SU_INPUT!"=="" set "PG_SUPERUSER=!PG_SU_INPUT!"

echo.
echo   You will be prompted for the !PG_SUPERUSER! password.
echo.

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
if errorlevel 1 echo   WARNING: GRANT failed (non-critical if DB already exists).
echo   Database step complete.
echo.

REM --- 3c: Write .env ---
:write_env
echo   Writing .env configuration...

if exist ".env" copy ".env" ".env.backup" >nul & echo   (.env backed up to .env.backup)

set "DATABASE_URL=postgresql://!PG_USER!:!PG_PASSWORD!@!PG_HOST!:!PG_PORT!/!PG_DBNAME!"

(
echo # iDRS Environment Configuration
echo # KEEP THIS FILE SECURE - contains database credentials
echo.
echo SECRET_KEY=
echo DEBUG=False
echo USE_HTTPS=False
echo.
echo ALLOWED_HOSTS=localhost,127.0.0.1,10.212.64.16,0.0.0.0
echo.
echo # PostgreSQL
echo DATABASE_URL=!DATABASE_URL!
echo.
echo # LDAP  (ONGC Active Directory)
echo LDAP_SERVER=ldap://10.205.48.230:389
echo LDAP_BASE_DN=DC=ONGC,DC=ONGCGroup,DC=co,DC=in
echo LDAP_USE_SSL=False
echo LDAP_VERIFY_SSL=False
echo LDAP_DOMAIN=ongcgroup.co.in
) > ".env"

if errorlevel 1 goto :err_env
echo   .env written.
echo.

REM --- 3d: Test TCP connectivity ---
echo   Testing TCP connection to PostgreSQL at !PG_HOST!:!PG_PORT!...
python -c "import socket; s=socket.create_connection(('!PG_HOST!',int('!PG_PORT!')),timeout=5); s.close()" >nul 2>&1
if errorlevel 1 goto :fix_pg_tcp
echo   TCP connection OK.
echo.
goto :step4_migrate

REM --- Auto-fix PostgreSQL TCP ---
:fix_pg_tcp
echo.
echo   PostgreSQL port !PG_PORT! not reachable. Attempting auto-fix...
echo.

set "PG_DATA="
set "PG_SVC_NAME="

if exist "C:\Program Files\PostgreSQL\17\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\17\data" & set "PG_SVC_NAME=postgresql-x64-17"
if "!PG_DATA!"=="" if exist "C:\Program Files\PostgreSQL\16\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\16\data" & set "PG_SVC_NAME=postgresql-x64-16"
if "!PG_DATA!"=="" if exist "C:\Program Files\PostgreSQL\15\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\15\data" & set "PG_SVC_NAME=postgresql-x64-15"
if "!PG_DATA!"=="" if exist "C:\Program Files\PostgreSQL\14\data\postgresql.conf" set "PG_DATA=C:\Program Files\PostgreSQL\14\data" & set "PG_SVC_NAME=postgresql-x64-14"

if "!PG_DATA!"=="" goto :fix_pg_manual

echo   Found PG data dir: !PG_DATA!
echo.

echo   Patching postgresql.conf: listen_addresses = '*'
echo. >> "!PG_DATA!\postgresql.conf"
echo # iDRS auto-fix >> "!PG_DATA!\postgresql.conf"
echo listen_addresses = '*' >> "!PG_DATA!\postgresql.conf"
echo port = !PG_PORT! >> "!PG_DATA!\postgresql.conf"

echo   Patching pg_hba.conf: allow TCP connections
echo. >> "!PG_DATA!\pg_hba.conf"
echo # iDRS auto-fix >> "!PG_DATA!\pg_hba.conf"
echo host    all             all             0.0.0.0/0               md5 >> "!PG_DATA!\pg_hba.conf"

echo   Opening Windows Firewall for port !PG_PORT!...
netsh advfirewall firewall delete rule name="PostgreSQL iDRS" >nul 2>&1
netsh advfirewall firewall add rule name="PostgreSQL iDRS" dir=in action=allow protocol=TCP localport=!PG_PORT! >nul 2>&1

echo   Restarting PostgreSQL service: !PG_SVC_NAME!...
net stop "!PG_SVC_NAME!" >nul 2>&1
net start "!PG_SVC_NAME!"
if errorlevel 1 goto :err_pg_restart

echo   Waiting 5 seconds...
timeout /t 5 /nobreak >nul

python -c "import socket; s=socket.create_connection(('!PG_HOST!',int('!PG_PORT!')),timeout=8); s.close()" >nul 2>&1
if errorlevel 1 goto :err_pg_tcp_retry
echo   PostgreSQL TCP connection now working!
echo.
goto :step4_migrate

:fix_pg_manual
echo ============================================================
echo  Could not find PostgreSQL data directory.
echo  Fix manually:
echo    1. Edit postgresql.conf: listen_addresses = '*'
echo    2. Edit pg_hba.conf: host all all 0.0.0.0/0 md5
echo    3. Open firewall: netsh advfirewall firewall add rule
echo       name="PostgreSQL" dir=in action=allow protocol=TCP localport=!PG_PORT!
echo    4. Restart PostgreSQL service, then re-run this script.
echo ============================================================
pause
exit /b 1

REM ============================================================================
REM [4] DJANGO MIGRATIONS
REM ============================================================================
:step4_migrate
echo [4/7] Running Django migrations...
echo.

python manage.py migrate --verbosity=1
if errorlevel 1 goto :err_migrate
echo   Migrations complete.
echo.

REM ============================================================================
REM [5] STATIC FILES
REM ============================================================================
echo [5/7] Collecting static files...
echo.

python manage.py collectstatic --noinput
if errorlevel 1 echo   WARNING: collectstatic had issues - CSS/JS may not render correctly.
if not errorlevel 1 echo   Static files collected.
echo.

REM --- Open Windows Firewall for iDRS web server port 8022 ---
echo   Opening Windows Firewall for iDRS web server (port 8022)...
netsh advfirewall firewall delete rule name="iDRS Web Server" >nul 2>&1
netsh advfirewall firewall add rule name="iDRS Web Server" dir=in action=allow protocol=TCP localport=8022 >nul 2>&1
if errorlevel 1 (
    echo   WARNING: Could not add firewall rule for port 8022.
    echo   If you need remote access to the app, run as Administrator or add manually:
    echo     netsh advfirewall firewall add rule name="iDRS Web Server" dir=in action=allow protocol=TCP localport=8022
) else (
    echo   Firewall rule added: port 8022 open for incoming connections.
)
echo.

REM ============================================================================
REM [6] LOAD FIXTURE DATA
REM ============================================================================
echo [6/7] Loading fixture data...
echo.

if not exist "fixtures" goto :no_fixtures

echo   Choose what to load:
echo     1) All data  (IDT Norms + MPI + AuthorizedUser)  ~5 min
echo     2) All EXCEPT large tables  (fast, ~30 sec)
echo     3) Skip data loading  (do manually later)
echo.
set /p LOAD_CHOICE="  Enter choice [1/2/3, default 1]: "
if "!LOAD_CHOICE!"=="3" goto :skip_fixtures
if "!LOAD_CHOICE!"=="2" goto :load_small

echo.
echo   Loading all fixture data (this takes a few minutes)...
python manage.py load_all_data
if errorlevel 1 echo   WARNING: Some fixtures had errors - see output above.
goto :step7_superuser

:load_small
echo.
echo   Loading fixtures (skipping large tables)...
python manage.py load_all_data --skip-large
if errorlevel 1 echo   WARNING: Some fixtures had errors - see output above.
goto :step7_superuser

:no_fixtures
echo   fixtures\ folder not found - skipping data load.
echo   Copy the fixtures folder from the Mac and run:
echo     python manage.py load_all_data
echo.
goto :step7_superuser

:skip_fixtures
echo   Skipping data load.
echo   Run later:  python manage.py load_all_data
echo.

REM ============================================================================
REM [7] SUPERUSER
REM ============================================================================
:step7_superuser
echo [7/7] Create Django admin superuser
echo.
set /p CREATE_SU="  Create admin superuser now? (Y/N, default Y): "
if /i "!CREATE_SU!"=="N" goto :done

python manage.py createsuperuser
if errorlevel 1 echo   NOTE: If username already exists, that is normal.
echo.

REM ============================================================================
REM DONE
REM ============================================================================
:done
echo.
echo ============================================================
echo  Setup Complete!
echo ============================================================
echo.
echo  Database : !PG_DBNAME! on !PG_HOST!:!PG_PORT!
echo  Config   : .env
echo  LDAP     : ldap://10.205.48.230:389
echo.
echo  Start the server:
echo    "Install Windows\run_server.bat"
echo.
echo  Access:
echo    http://10.212.64.16:8022
echo    http://localhost:8022
echo.
echo  Admin panel:
echo    http://10.212.64.16:8022/admin
echo.
echo  LDAP troubleshooting:
echo    "Install Windows\diagnose_ldap.bat"
echo.
pause
exit /b 0

REM ============================================================================
REM ERROR LABELS
REM ============================================================================

:err_no_managepy
echo ERROR: manage.py not found in current directory.
echo Run this from the iDRS project root (where manage.py lives).
pause
exit /b 1

:err_no_python
echo ERROR: Python not found. Install Python 3.13.9 and add to PATH.
pause
exit /b 1

:err_venv_create
echo ERROR: Could not create virtual environment.
pause
exit /b 1

:err_no_packages
echo ERROR: offline_packages\ folder not found.
echo Copy it from the Mac deployment folder.
pause
exit /b 1

:err_django_missing
echo ERROR: Django not installed. Check offline_packages folder.
pause
exit /b 1

:err_no_psql
echo Setup cancelled. Install PostgreSQL or create the DB via pgAdmin first.
pause
exit /b 1

:err_psql_user
del "!SETUP_SQL!" 2>nul
echo.
echo ERROR: Could not create PostgreSQL role "!PG_USER!"
echo Check superuser password and that PostgreSQL is running.
pause
exit /b 1

:err_psql_db
echo.
echo ERROR: Could not create database "!PG_DBNAME!"
echo Create manually: CREATE DATABASE !PG_DBNAME! OWNER !PG_USER!;
pause
exit /b 1

:err_env
echo ERROR: Could not write .env file. Check folder permissions.
pause
exit /b 1

:err_pg_restart
echo.
echo ERROR: Could not restart PostgreSQL service "!PG_SVC_NAME!"
echo Open services.msc and restart it manually, then re-run this script.
pause
exit /b 1

:err_pg_tcp_retry
echo.
echo ERROR: PostgreSQL still not reachable at !PG_HOST!:!PG_PORT! after auto-fix.
echo Check: services.msc, postgresql.conf, pg_hba.conf, and firewall.
pause
exit /b 1

:err_migrate
echo.
echo ERROR: Django migrations failed. See traceback above.
echo DATABASE_URL: !DATABASE_URL!
echo Test: psql -h !PG_HOST! -p !PG_PORT! -U !PG_USER! -d !PG_DBNAME!
pause
exit /b 1
