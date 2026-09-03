@echo off
setlocal EnableDelayedExpansion
title iDRS - LDAP Diagnostics
REM ============================================================================
REM iDRS - LDAP Diagnostics and Fix Script
REM Run from the iDRS application root folder (where manage.py lives)
REM Run as Administrator for best results
REM ============================================================================
REM
REM What this script tests and fixes (in order):
REM   [1] ldap3 Python package installed in venv
REM   [2] .env file exists and has correct LDAP settings
REM   [3] TCP connectivity to LDAP server (10.205.48.230:389)
REM   [4] Actual LDAP bind (anonymous + user bind)
REM   [5] AuthorizedUser table has records (not empty)
REM   [6] A test CPF number exists and has a role
REM   [7] Full LDAP login simulation for one user
REM ============================================================================

echo.
echo ============================================================
echo  iDRS - LDAP Diagnostics and Fix
echo ============================================================
echo.

if not exist "manage.py" (
    echo ERROR: manage.py not found.
    echo Run this script from the iDRS project root folder.
    echo   e.g.  cd "C:\Users\Administrator\Desktop\iDRS Postgres"
    echo         "Install Windows\diagnose_ldap.bat"
    pause
    exit /b 1
)
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Run install_offline_simple.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
echo   Virtual environment: OK
echo.

REM ============================================================================
REM [1] Check ldap3 package
REM ============================================================================
echo [1/7] Checking ldap3 package...
python -c "import ldap3; print('  ldap3 version:', ldap3.__version__)" 2>nul
if errorlevel 1 (
    echo   ldap3 NOT installed. Installing from offline_packages...
    if not exist "offline_packages\ldap3-2.9.1-py2.py3-none-any.whl" (
        echo.
        echo   ERROR: ldap3 wheel not found in offline_packages\
        echo   Expected: offline_packages\ldap3-2.9.1-py2.py3-none-any.whl
        echo   Copy the offline_packages folder from the Mac and retry.
        pause
        exit /b 1
    )
    python -m pip install --no-index --find-links=offline_packages ldap3 pyasn1
    if errorlevel 1 (
        echo   ERROR: ldap3 installation failed. See output above.
        pause
        exit /b 1
    )
    python -c "import ldap3; print('  ldap3 installed successfully:', ldap3.__version__)"
) else (
    echo   ldap3: OK
)
echo.

REM ============================================================================
REM [2] Check .env LDAP settings
REM ============================================================================
echo [2/7] Checking .env LDAP configuration...
if not exist ".env" (
    echo   WARNING: .env file not found.
    echo   Creating default .env with LDAP settings...
    goto :write_env
)

REM Read current .env and show LDAP-related lines
echo   Current .env LDAP settings:
findstr /i "LDAP" .env
echo.

REM Check each required LDAP variable
set "ENV_OK=1"
findstr /i "LDAP_SERVER" .env >nul 2>&1
if errorlevel 1 (
    echo   MISSING: LDAP_SERVER
    set "ENV_OK=0"
)
findstr /i "LDAP_BASE_DN" .env >nul 2>&1
if errorlevel 1 (
    echo   MISSING: LDAP_BASE_DN
    set "ENV_OK=0"
)
findstr /i "LDAP_DOMAIN" .env >nul 2>&1
if errorlevel 1 (
    echo   MISSING: LDAP_DOMAIN
    set "ENV_OK=0"
)

if "!ENV_OK!"=="0" (
    echo.
    echo   Some LDAP vars missing from .env. Appending defaults...
    goto :append_ldap_env
)

echo   .env LDAP settings: OK
goto :step3

:write_env
echo   Writing .env with default LDAP settings...
(
echo # iDRS Environment Configuration
echo DEBUG=False
echo SECRET_KEY=
echo ALLOWED_HOSTS=localhost,127.0.0.1,10.212.64.16,0.0.0.0
echo.
echo # Set DATABASE_URL to your PostgreSQL connection string
echo DATABASE_URL=postgresql://idrs_user:subrat19@10.212.64.16:5432/idrs_db
echo.
echo LDAP_SERVER=ldap://10.205.48.230:389
echo LDAP_BASE_DN=DC=ONGC,DC=ONGCGroup,DC=co,DC=in
echo LDAP_USE_SSL=False
echo LDAP_VERIFY_SSL=False
echo LDAP_DOMAIN=ongcgroup.co.in
) > ".env"
echo   .env created.
goto :step3

:append_ldap_env
echo. >> ".env"
echo # LDAP settings - appended by diagnose_ldap.bat >> ".env"
findstr /i "LDAP_SERVER" .env >nul 2>&1
if errorlevel 1 echo LDAP_SERVER=ldap://10.205.48.230:389 >> ".env"
findstr /i "LDAP_BASE_DN" .env >nul 2>&1
if errorlevel 1 echo LDAP_BASE_DN=DC=ONGC,DC=ONGCGroup,DC=co,DC=in >> ".env"
findstr /i "LDAP_USE_SSL" .env >nul 2>&1
if errorlevel 1 echo LDAP_USE_SSL=False >> ".env"
findstr /i "LDAP_VERIFY_SSL" .env >nul 2>&1
if errorlevel 1 echo LDAP_VERIFY_SSL=False >> ".env"
findstr /i "LDAP_DOMAIN" .env >nul 2>&1
if errorlevel 1 echo LDAP_DOMAIN=ongcgroup.co.in >> ".env"
echo   LDAP settings appended to .env

:step3
echo.

REM ============================================================================
REM [3] TCP connectivity to LDAP server
REM ============================================================================
echo [3/7] Testing TCP connectivity to LDAP server (10.205.48.230:389)...
python -c "import socket; s=socket.create_connection(('10.205.48.230',389),timeout=5); s.close(); print('  TCP connection to 10.205.48.230:389 SUCCESS')" 2>nul
if errorlevel 1 (
    echo.
    echo   ============================================================
    echo   FAIL: Cannot reach LDAP server at 10.205.48.230:389
    echo.
    echo   This VM (10.212.64.16) cannot connect to the LDAP/AD server.
    echo.
    echo   Possible causes:
    echo     A) This VM is not on the corporate network that can reach
    echo        10.205.48.230. Ensure network/VPN connectivity.
    echo     B) Windows Firewall on this VM is blocking outbound port 389.
    echo        Fix: Allow outbound TCP 389 in Windows Firewall.
    echo     C) The LDAP server address has changed.
    echo        Check with the IT/AD team for the correct address.
    echo.
    echo   To open outbound firewall for LDAP (run as Admin):
    echo     netsh advfirewall firewall add rule name="LDAP Outbound" ^
    echo       dir=out action=allow protocol=TCP remoteport=389
    echo.
    echo   Test from Command Prompt:
    echo     telnet 10.205.48.230 389
    echo     (If telnet not installed: Enable-WindowsOptionalFeature -Online ^
    echo       -FeatureName TelnetClient)
    echo.
    echo   Cannot proceed with LDAP tests until connectivity is fixed.
    echo   ============================================================
    echo.
    echo   Attempting to add outbound firewall rule now...
    netsh advfirewall firewall delete rule name="iDRS LDAP Outbound" >nul 2>&1
    netsh advfirewall firewall add rule name="iDRS LDAP Outbound" dir=out action=allow protocol=TCP remoteport=389 >nul 2>&1
    if not errorlevel 1 echo   Firewall rule added - retry TCP test...
    REM Re-test after adding rule
    python -c "import socket; s=socket.create_connection(('10.205.48.230',389),timeout=5); s.close()" 2>nul
    if errorlevel 1 (
        echo   Still unreachable. Network routing issue - cannot fix via script.
        echo   Skipping LDAP connectivity tests [4].
        goto :step5
    ) else (
        echo   TCP connection now working after firewall fix.
    )
) else (
    echo   TCP connection to LDAP server: OK
)
echo.

REM ============================================================================
REM [4] LDAP bind test
REM ============================================================================
echo [4/7] Testing LDAP server response (anonymous info read)...
python -c "
from ldap3 import Server, ALL, Connection, ANONYMOUS
try:
    s = Server('ldap://10.205.48.230:389', get_info=ALL, connect_timeout=5)
    c = Connection(s, authentication=ANONYMOUS, receive_timeout=5)
    c.open()
    print('  LDAP server reachable and responding.')
    if s.info:
        print('  Server info obtained: OK')
    c.unbind()
except Exception as e:
    print('  LDAP server error:', type(e).__name__, str(e)[:120])
" 2>&1
echo.

REM ============================================================================
REM [5] Check AuthorizedUser table
REM ============================================================================
:step5
echo [5/7] Checking AuthorizedUser table in PostgreSQL...
python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE']='drilling_scheduler.settings'
django.setup()
from scheduler.models import AuthorizedUser
from django.db.models import Count
total = AuthorizedUser.objects.count()
active = AuthorizedUser.objects.filter(is_active=True).count()
with_role = AuthorizedUser.objects.exclude(role='').count()
no_role = total - with_role
print(f'  Total  AuthorizedUser rows : {total}')
print(f'  Active (is_active=True)    : {active}')
print(f'  Have role assigned         : {with_role}')
print(f'  Missing role (blocked!)    : {no_role}')
if total == 0:
    print()
    print('  CRITICAL: AuthorizedUser table is EMPTY.')
    print('  No one can log in. Load fixtures first:')
    print('    Install Windows\load_data.bat')
    sys.exit(2)
elif no_role > 0:
    print()
    print(f'  WARNING: {no_role} users have no role set and cannot log in.')
    print('  Fix: python manage.py set_user_role --cpf <CPF> --role user')
else:
    print('  AuthorizedUser table: OK')
" 2>&1
echo.

REM ============================================================================
REM [6] Check a specific CPF (prompt user)
REM ============================================================================
echo [6/7] Check a specific user's authorization status...
echo.
set /p TEST_CPF="Enter a CPF number to test (or ENTER to skip): "
if "!TEST_CPF!"=="" goto :step7

python -c "
import django, os
os.environ['DJANGO_SETTINGS_MODULE']='drilling_scheduler.settings'
django.setup()
from scheduler.models import AuthorizedUser
cpf = '!TEST_CPF!'.strip()
try:
    u = AuthorizedUser.objects.get(cpf_no=cpf)
    print(f'  Found: {u.cpf_no}  -  {u.name}')
    print(f'  Role          : {u.role!r}')
    print(f'  is_active     : {u.is_active}')
    print(f'  Location      : {u.assigned_location!r}')
    print(f'  Linked user   : {u.user}')
    if not u.is_active:
        print('  STATUS: BLOCKED - user is inactive')
    elif not u.role or u.role.strip() == '':
        print('  STATUS: BLOCKED - no role assigned')
    else:
        print('  STATUS: Authorized to log in (if LDAP password is correct)')
except AuthorizedUser.DoesNotExist:
    print(f'  NOT FOUND: CPF {cpf} is not in the AuthorizedUser table.')
    print('  This user cannot log in.')
    print('  Fix: Add them via Django Admin or sync_mpi_to_authorized_users command.')
" 2>&1
echo.

REM ============================================================================
REM [7] Full authentication simulation
REM ============================================================================
:step7
echo [7/7] Full authentication simulation (no password needed)...
echo.
set /p SIM_CPF="Enter CPF to simulate auth flow (or ENTER to skip): "
if "!SIM_CPF!"=="" goto :summary

set /p SIM_PASS="Enter password for CPF !SIM_CPF! (will test against LDAP): "
if "!SIM_PASS!"=="" (
    echo   Skipping LDAP bind test - no password provided.
    goto :summary
)

python -c "
import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE']='drilling_scheduler.settings'
django.setup()
from django.conf import settings
from scheduler.models import AuthorizedUser
from ldap3 import Server, Connection, ALL, SIMPLE, SUBTREE
from ldap3.core.exceptions import LDAPInvalidCredentialsResult, LDAPSocketOpenError

cpf = '!SIM_CPF!'.strip()
pwd = '!SIM_PASS!'.strip()

# Step 1: AuthorizedUser check
print(f'  Testing login for CPF: {cpf}')
print()
try:
    au = AuthorizedUser.objects.get(cpf_no=cpf)
    print(f'  [PASS] AuthorizedUser exists: {au.name}')
    print(f'         role={au.role!r}  active={au.is_active}')
    if not au.is_active:
        print('  [FAIL] User is inactive - cannot log in')
        sys.exit(1)
    if not au.role or au.role.strip() == '':
        print('  [FAIL] User has no role - cannot log in')
        sys.exit(1)
except AuthorizedUser.DoesNotExist:
    print(f'  [FAIL] CPF {cpf} not in AuthorizedUser table')
    sys.exit(1)

# Step 2: LDAP bind
print()
print('  Attempting LDAP bind...')
server = Server(settings.LDAP_SERVER, use_ssl=False, get_info=ALL, connect_timeout=5)
formats = [
    cpf,
    f'{cpf}@ONGC.ONGCGroup.co.in',
    f'ONGCGROUP\\\\{cpf}',
]
success = False
for fmt in formats:
    try:
        conn = Connection(server, user=fmt, password=pwd, authentication=SIMPLE,
                         auto_bind=True, raise_exceptions=True, receive_timeout=5)
        print(f'  [PASS] LDAP bind SUCCESS with format: {fmt}')
        conn.unbind()
        success = True
        break
    except LDAPInvalidCredentialsResult:
        print(f'  [FAIL] Invalid credentials with format: {fmt}')
    except LDAPSocketOpenError as e:
        print(f'  [FAIL] Cannot connect to LDAP server: {e}')
        break
    except Exception as e:
        print(f'  [FAIL] {type(e).__name__}: {str(e)[:80]}')

if success:
    print()
    print('  RESULT: Login will SUCCEED for this user.')
else:
    print()
    print('  RESULT: Login will FAIL.')
    print('          Check credentials or LDAP server connectivity.')
" 2>&1
echo.

REM ============================================================================
REM Summary
REM ============================================================================
:summary
echo ============================================================
echo  LDAP Diagnostic complete.
echo ============================================================
echo.
echo  If all tests passed, LDAP login should work.
echo.
echo  Most common failure reasons and fixes:
echo.
echo  1. AuthorizedUser table empty:
echo       "Install Windows\load_data.bat"  (loads all fixtures)
echo.
echo  2. ldap3 not installed:
echo       python -m pip install --no-index --find-links=offline_packages ldap3 pyasn1
echo.
echo  3. LDAP server unreachable (10.205.48.230:389):
echo       - Ensure this VM is on the ONGC corporate network
echo       - Or check with IT for the correct LDAP server IP
echo.
echo  4. User not in AuthorizedUser:
echo       - Wait for load_data.bat to finish
echo       - Or add via Django Admin: http://10.212.64.16:8022/admin
echo.
echo  5. User has no role (AuthorizedUser.role is blank):
echo       Update via Django Admin: http://10.212.64.16:8022/admin
echo         "Authorized users" --^> find by CPF --^> set Role to "user"
echo       Or run:
echo         python manage.py shell -c "from scheduler.models import AuthorizedUser; "
echo         "  AuthorizedUser.objects.filter(role='').update(role='user')"
echo.
echo  6. View LDAP auth logs:
echo       type logs\ldap_auth.log
echo.
pause
exit /b 0
