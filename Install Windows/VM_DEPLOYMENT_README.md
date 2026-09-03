# iDRS - Windows VM Deployment Guide

## Overview
Complete deployment package for Interactive Drilling Rig Scheduler (iDRS) on an **offline Windows VM** running Python 3.13.9.

**Target VM IP:** 10.212.64.16

---

## Prerequisites

### Required Software
- **Python 3.13.9** (64-bit) for Windows
  - Download from: https://www.python.org/downloads/
  - **IMPORTANT:** During installation, check "Add Python to PATH"

### System Requirements
- Windows 10 or Windows Server 2016 or later
- Minimum 4GB RAM
- 2GB free disk space

---

## Deployment Package Contents

```
IDRS v9/
├── Install Windows/
│   ├── DEPLOY_VM.bat          ← USE THIS FOR COMPLETE DEPLOYMENT
│   ├── start_server.bat       ← Start the server after deployment
│   ├── install_offline_simple.bat
│   ├── setup_database.bat
│   └── setup_windows.bat
├── offline_packages/          ← All Python wheels (NO INTERNET NEEDED)
│   ├── Django-5.1.5-py3-none-any.whl
│   ├── numpy-2.4.1-cp313-cp313-win_amd64.whl
│   ├── ortools-9.15.6755-cp313-cp313-win_amd64.whl
│   ├── Pillow-12.1.0-cp313-cp313-win_amd64.whl  ← Added for video thumbnails
│   └── ... (26+ dependency packages)
├── manage.py
├── db.sqlite3                 ← Database (will be created on first run)
├── drilling_scheduler/
├── scheduler/
├── templates/
├── static/
└── media/                     ← Video tutorials and thumbnails
    └── tutorials/
        ├── videos/
        └── thumbnails/
```

---

## Quick Start Deployment (Recommended)

### Step 1: Install Python 3.13.9
1. Download Python 3.13.9 for Windows (64-bit)
2. Run the installer
3. **CHECK** "Add Python to PATH"
4. Click "Install Now"
5. Verify installation:
   ```cmd
   python --version
   ```
   Should show: `Python 3.13.9`

### Step 2: Copy Files to VM
Transfer the entire `IDRS v9` folder to your Windows VM at any location, e.g.:
```
C:\iDRS\
```

**IMPORTANT:** Ensure all offline packages are present, including:
- `Pillow-12.1.0-cp313-cp313-win_amd64.whl` (for video thumbnails)
- All other packages listed in `requirements.txt`

If any packages are missing, download them from https://pypi.org/ using a machine with internet access.

### Step 3: Run Complete Deployment
1. Open Command Prompt as Administrator
2. Navigate to the project folder:
   ```cmd
   cd C:\iDRS
   ```
3. Run the deployment script:
   ```cmd
   "Install Windows\DEPLOY_VM.bat"
   ```

The script will automatically:
- ✅ Create Python virtual environment
- ✅ Install ALL dependencies from offline packages (no internet needed)
- ✅ Setup SQLite database
- ✅ Collect static files
- ✅ Prompt you to create an admin user

### Step 4: Create Admin Account
When prompted, create your admin user:
```
Username: admin
Email address: (leave blank or enter email)
Password: ******** (minimum 8 characters)
Password (again): ********
```

### Step 5: Start the Server
After deployment completes:
```cmd
"Install Windows\start_server.bat"
```

The server will start on **port 8022** and be accessible at:
- **Local access:** http://localhost:8022
- **Network access:** http://10.212.64.16:8022
- **Admin panel:** http://10.212.64.16:8022/admin

---

## Manual Deployment (Alternative)

If you prefer step-by-step manual deployment:

### 1. Create Virtual Environment
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### 2. Install Dependencies
```cmd
"Install Windows\install_offline_simple.bat"
```

### 3. Setup Database
```cmd
"Install Windows\setup_database.bat"
```

### 4. Start Server
```cmd
"Install Windows\start_server.bat"
```

---

## Configuration

### Server Access
The application is pre-configured to accept connections from:
- `localhost`
- `127.0.0.1`
- `0.0.0.0`
- `10.212.64.16` (your VM IP)

### Change Port
To run on a different port:
```cmd
"Install Windows\start_server.bat" 8000
```

### Network Access
The server binds to `0.0.0.0:8022` which allows access from:
- The VM itself
- Other machines on the network via `http://10.212.64.16:8022`

---

## Testing the Deployment

### 1. Local Access Test
On the VM, open a browser and go to:
```
http://localhost:8022
```

### 2. Network Access Test
From another computer on the network:
```
http://10.212.64.16:8022
```

### 3. Admin Panel Access
```
http://10.212.64.16:8022/admin
```
Login with the admin credentials you created.

---

## Troubleshooting

### Python Not Found
**Error:** `'python' is not recognized as an internal or external command`

**Solution:**
1. Reinstall Python 3.13.9
2. Make sure to check "Add Python to PATH"
3. Restart Command Prompt after installation

### Port Already in Use
**Error:** `Error: That port is already in use`

**Solution:**
```cmd
REM Find what's using port 8022
netstat -ano | findstr :8022

REM Use a different port
"Install Windows\start_server.bat" 8012
```

### Cannot Access from Network
**Problem:** Can access via localhost but not from network

**Solution:**
1. Check Windows Firewall settings
2. Add inbound rule for port 8022:
   ```
   Control Panel > Windows Defender Firewall > Advanced Settings
   > Inbound Rules > New Rule > Port > TCP > 8022 > Allow
   ```

### Virtual Environment Activation Issues
**Solution:**
Enable script execution in PowerShell (run as Administrator):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Database Migration Errors
**Solution:**
```cmd
.venv\Scripts\activate.bat
python manage.py migrate --run-syncdb
```

---

## Maintenance

### Starting the Server
```cmd
cd C:\iDRS
"Install Windows\start_server.bat"
```

### Stopping the Server
Press `Ctrl+C` in the Command Prompt window

### Creating Additional Users
```cmd
.venv\Scripts\activate.bat
python manage.py createsuperuser
```

### Backing Up Data
```cmd
REM Copy the database file
copy db.sqlite3 db.sqlite3.backup
```

### Viewing Logs
Logs are stored in the `logs/` folder

---

## Installed Packages

All packages are included in `offline_packages/` for Python 3.13.9:

| Package | Version | Purpose |
|---------|---------|---------|
| Django | 5.1.5 | Web framework |
| djangorestframework | 3.15.2 | REST API |
| django-cors-headers | 4.6.0 | CORS support |
| pandas | 2.2.3 | Data processing |
| numpy | 2.4.1 | Numerical computing |
| ortools | 9.15.6755 | Optimization engine |
| openpyxl | 3.1.5 | Excel support |
| plotly | 5.24.1 | Visualization |
| python-dotenv | 1.0.1 | Environment config |
| whitenoise | 6.8.2 | Static files |
| ldap3 | 2.9.1 | LDAP integration |
| psycopg2-binary | 2.9.11 | PostgreSQL support |
| pywin32 | 311 | Windows APIs |

Plus all dependencies (25+ total packages)

---

## Production Deployment Notes

### Security Considerations
For production deployment:

1. **Change SECRET_KEY**
   - Create `.env` file in project root
   - Add: `SECRET_KEY=your-secure-random-key-here`

2. **Disable DEBUG Mode**
   - In `.env`: `DEBUG=False`

3. **Use PostgreSQL** (optional, for better performance)
   - Install PostgreSQL on VM
   - Update database settings in `drilling_scheduler/settings.py`

4. **Setup HTTPS** (recommended)
   - Use IIS or nginx as reverse proxy
   - Configure SSL certificate

5. **Create Windows Service** (optional, for auto-start)
   - Use NSSM (Non-Sucking Service Manager)
   - Configure service to auto-start on boot

### Performance Optimization
```python
# In settings.py
DEBUG = False
ALLOWED_HOSTS = ['10.212.64.16', 'your-domain.com']
```

---

## Support Information

### Application Details
- **Name:** Interactive Drilling Rig Scheduler (iDRS)
- **Version:** 9
- **Python:** 3.13.9
- **Framework:** Django 5.1.5
- **Database:** SQLite (default) / PostgreSQL (optional)
- **Server IP:** 10.212.64.16
- **Server Port:** 8022

### Key Features
- Drilling rig scheduling and optimization
- Well assignment management
- Interactive Gantt chart visualization
- Excel import/export
- Real-time schedule updates
- REST API support

---

## Quick Reference Commands

```cmd
REM Navigate to project
cd C:\iDRS

REM Activate virtual environment
.venv\Scripts\activate.bat

REM Start development server
python manage.py runserver 0.0.0.0:8022

REM Create admin user
python manage.py createsuperuser

REM Database migrations
python manage.py migrate

REM Collect static files
python manage.py collectstatic

REM Check installed packages
pip list

REM Access application
start http://10.212.64.16:8022
```

---

## Success Checklist

- [ ] Python 3.13.9 installed and in PATH
- [ ] Project files copied to VM
- [ ] `DEPLOY_VM.bat` executed successfully
- [ ] Admin user created
- [ ] Server starts without errors
- [ ] Can access http://localhost:8022 on VM
- [ ] Can access http://10.212.64.16:8022 from network
- [ ] Can login to admin panel
- [ ] Firewall configured (if needed)

---

**Deployment Date:** January 2026  
**Target VM:** Windows VM @ 10.212.64.16  
**Python Version:** 3.13.9  
**Offline Installation:** ✅ All dependencies included
