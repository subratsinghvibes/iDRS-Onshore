# iDRS Windows Installation Guide

## 📋 Prerequisites

- Windows 10 or Windows Server 2016 or later
- Administrator access
- Python 3.13.9 installed
- At least 10 GB free disk space

## 🚀 Quick Start (3 Steps)

### Step 1: Install FFmpeg (REQUIRED)

FFmpeg is **required** for video tutorial features.

**Option A: Automated (Recommended if VM has internet)**
```cmd
download_ffmpeg.bat
install_ffmpeg.bat (Right-click → Run as Administrator)
```

**Option B: Manual (For offline VMs)**
See `FFMPEG_INSTALLATION_GUIDE.md` for detailed instructions.

**Verify:**
```cmd
ffmpeg -version
```

### Step 2: Install iDRS

```cmd
install_offline_simple.bat
```

This will:
- Create virtual environment
- Install all Python packages from offline_packages/
- Check FFmpeg installation
- Set up the application

### Step 3: Start Server

```cmd
start_server.bat
```

Access at: http://localhost:8022

## 📁 Installation Files

| File | Purpose |
|------|---------|
| `install_offline_simple.bat` | Main installation script |
| `download_ffmpeg.bat` | Download FFmpeg (requires internet) |
| `install_ffmpeg.bat` | Install FFmpeg to system |
| `start_server.bat` | Start the iDRS server |
| `setup_database.bat` | Initialize database |
| `verify_packages.bat` | Verify all packages installed |
| `FFMPEG_INSTALLATION_GUIDE.md` | Detailed FFmpeg guide |

## 🔧 Detailed Installation

### 1. FFmpeg Installation

**Why FFmpeg?**
- Required for automatic video compression
- Enables instant video streaming
- Reduces 700MB videos to 150-250MB
- Provides YouTube/Netflix-level performance

**Installation Methods:**

#### Method 1: Automated Download (Internet Required)
```cmd
# Step 1: Download
download_ffmpeg.bat

# Step 2: Install (as Administrator)
Right-click install_ffmpeg.bat → Run as administrator

# Step 3: Verify
ffmpeg -version
```

#### Method 2: Manual Installation (Offline)
```cmd
# Step 1: Download on another computer
Go to: https://github.com/BtbN/FFmpeg-Builds/releases
Download: ffmpeg-master-latest-win64-gpl.zip

# Step 2: Transfer to VM
Copy zip file to VM via USB/network

# Step 3: Extract
Extract to: C:\ffmpeg

# Step 4: Add to PATH
System Properties → Environment Variables → Path → Add: C:\ffmpeg\bin

# Step 5: Verify
ffmpeg -version
```

### 2. Python Package Installation

```cmd
# Run the installation script
install_offline_simple.bat
```

**What it does:**
1. Checks Python installation
2. Creates virtual environment (.venv)
3. Installs Django and dependencies
4. Installs video processing packages (moviepy, imageio, etc.)
5. Checks FFmpeg availability
6. Verifies installation

**If installation fails:**
- Check Python version: `python --version` (should be 3.13.x)
- Verify offline_packages folder exists
- Check for missing .whl files
- Run as Administrator if permission errors

### 3. Database Setup

```cmd
# Initialize database
setup_database.bat
```

**What it does:**
1. Creates database tables
2. Applies migrations
3. Creates superuser account
4. Loads initial data (optional)

**Default superuser:**
- Username: admin
- Password: (you'll be prompted to create)

### 4. Start Server

```cmd
# Start the development server
start_server.bat
```

**Access the application:**
- Local: http://localhost:8022
- Network: http://[VM-IP]:8022

**For production:**
- Use `start_server.bat` for testing
- For production, configure as Windows Service
- See `VM_DEPLOYMENT_README.md` for details

## ✅ Verification

### Check Installation Status

```cmd
verify_packages.bat
```

This checks:
- ✅ Python version
- ✅ Virtual environment
- ✅ Django installation
- ✅ All required packages
- ✅ FFmpeg availability
- ✅ Database status

### Test Video Processing

1. **Start server:** `start_server.bat`
2. **Login as admin:** http://localhost:8022/admin
3. **Upload test video:** Scheduler → Video Tutorials → Add
4. **Check processing:** Should show "Processing" then "Completed"
5. **Test playback:** Go to Video Tutorials page

## 🔍 Troubleshooting

### FFmpeg Not Found

**Symptom:** Warning about FFmpeg during installation

**Solutions:**
1. Install FFmpeg using `install_ffmpeg.bat`
2. Verify: `ffmpeg -version`
3. Restart command prompt
4. If still not found, add to PATH manually

### Package Installation Fails

**Symptom:** Error installing packages from offline_packages

**Solutions:**
1. Check offline_packages folder exists
2. Verify all .whl files are present
3. Check Python version matches (3.13)
4. Try installing packages individually:
   ```cmd
   .venv\Scripts\activate
   pip install --no-index --find-links=offline_packages Django
   ```

### Video Processing Fails

**Symptom:** Videos don't get compressed after upload

**Solutions:**
1. Check FFmpeg: `ffmpeg -version`
2. Check server logs: `logs\django.log`
3. Verify video file format (MP4 recommended)
4. Check disk space (needs 2-3x video size)

### Server Won't Start

**Symptom:** Error when running start_server.bat

**Solutions:**
1. Check port 8022 is not in use
2. Verify database exists: `db.sqlite3`
3. Run migrations: `setup_database.bat`
4. Check logs: `logs\django.log`

### Permission Errors

**Symptom:** "Access denied" or "Permission denied"

**Solutions:**
1. Run Command Prompt as Administrator
2. Check folder permissions
3. Disable antivirus temporarily
4. Check Windows Firewall settings

## 📊 System Requirements

### Minimum Requirements
- **OS:** Windows 10 / Server 2016
- **CPU:** 2 cores
- **RAM:** 4 GB
- **Disk:** 10 GB free space
- **Python:** 3.13.9

### Recommended Requirements
- **OS:** Windows 10/11 / Server 2019/2022
- **CPU:** 4+ cores (for video processing)
- **RAM:** 8+ GB
- **Disk:** 50+ GB free space (SSD preferred)
- **Python:** 3.13.9

### Network Requirements
- **For Installation:** Internet access (for FFmpeg download) OR offline packages
- **For Operation:** Local network access
- **Ports:** 8022 (default, configurable)

## 🎯 Post-Installation

### 1. Create Admin User

```cmd
.venv\Scripts\activate
python manage.py createsuperuser
```

### 2. Configure Settings

Edit `.env` file:
```
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,[VM-IP]
SECRET_KEY=[generate-new-key]
```

### 3. Collect Static Files

```cmd
.venv\Scripts\activate
python manage.py collectstatic --noinput
```

### 4. Test Video Upload

1. Login to admin panel
2. Upload a test video
3. Wait for processing (1-10 minutes)
4. Check status shows "Completed"
5. Test playback on client PC

### 5. Configure for Production

For production deployment:
- Set DEBUG=False
- Use strong SECRET_KEY
- Configure ALLOWED_HOSTS
- Set up Windows Service
- Configure firewall rules
- Enable HTTPS (optional)

See `VM_DEPLOYMENT_README.md` for production setup.

## 📞 Support

### Common Issues

| Issue | Solution |
|-------|----------|
| FFmpeg not found | Install using install_ffmpeg.bat |
| Package install fails | Check offline_packages folder |
| Video processing fails | Verify FFmpeg installation |
| Server won't start | Check port 8022 availability |
| Permission denied | Run as Administrator |

### Log Files

Check these for errors:
- `logs\django.log` - Application logs
- `logs\ldap_auth.log` - Authentication logs

### Getting Help

1. Check this README
2. Check FFMPEG_INSTALLATION_GUIDE.md
3. Check OFFLINE_DEPLOYMENT_CHECKLIST.md
4. Check server logs
5. Verify all prerequisites met

## ✅ Success Checklist

Installation is successful when:

- [ ] Python 3.13.9 installed
- [ ] FFmpeg installed and in PATH
- [ ] Virtual environment created
- [ ] All packages installed
- [ ] Database initialized
- [ ] Server starts without errors
- [ ] Can access http://localhost:8022
- [ ] Can login to admin panel
- [ ] Can upload and process videos
- [ ] Videos play on client PCs

## 🎬 Next Steps

After successful installation:

1. **Upload video tutorials** through admin panel
2. **Configure user accounts** and permissions
3. **Import wells and rigs** data
4. **Set up scheduling** parameters
5. **Train users** on the system

Enjoy using iDRS!
