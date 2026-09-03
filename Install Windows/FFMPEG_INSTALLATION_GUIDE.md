# FFmpeg Installation Guide for Windows

FFmpeg is **REQUIRED** for video tutorial features in iDRS. This guide provides multiple installation methods.

## 🚀 Quick Installation (Recommended)

### Method 1: Automated Installation (Easiest)

1. **Download FFmpeg:**
   ```cmd
   download_ffmpeg.bat
   ```
   This will download FFmpeg automatically (requires internet).

2. **Install FFmpeg:**
   ```cmd
   Right-click install_ffmpeg.bat → Run as Administrator
   ```
   This will install FFmpeg to `C:\ffmpeg` and add it to PATH.

3. **Verify Installation:**
   ```cmd
   ffmpeg -version
   ```
   You should see FFmpeg version information.

### Method 2: Manual Installation

If the automated method doesn't work, follow these steps:

#### Step 1: Download FFmpeg

1. Go to: https://github.com/BtbN/FFmpeg-Builds/releases
2. Download: **ffmpeg-master-latest-win64-gpl.zip**
3. Save to your Downloads folder

#### Step 2: Extract FFmpeg

1. Right-click the downloaded zip file
2. Select "Extract All..."
3. Extract to: `C:\ffmpeg`
4. You should have: `C:\ffmpeg\bin\ffmpeg.exe`

#### Step 3: Add to System PATH

1. **Open System Properties:**
   - Press `Windows + R`
   - Type: `sysdm.cpl`
   - Press Enter

2. **Edit Environment Variables:**
   - Click "Advanced" tab
   - Click "Environment Variables" button
   - Under "System variables", find "Path"
   - Click "Edit"

3. **Add FFmpeg:**
   - Click "New"
   - Type: `C:\ffmpeg\bin`
   - Click "OK" on all windows

4. **Restart Command Prompt:**
   - Close all command prompt windows
   - Open a new command prompt
   - Test: `ffmpeg -version`

### Method 3: Using Chocolatey (If Available)

If you have Chocolatey package manager installed:

```cmd
choco install ffmpeg
```

### Method 4: Using Winget (Windows 10/11)

If you have winget (Windows Package Manager):

```cmd
winget install ffmpeg
```

## ✅ Verification

After installation, verify FFmpeg is working:

```cmd
ffmpeg -version
```

You should see output like:
```
ffmpeg version N-xxxxx-gxxxxxxx
built with gcc x.x.x
configuration: --enable-gpl ...
```

## 🔧 Troubleshooting

### FFmpeg Not Found After Installation

**Problem:** Running `ffmpeg -version` shows "command not found"

**Solutions:**

1. **Restart Command Prompt:**
   - Close all command prompt windows
   - Open a new one
   - Try again

2. **Restart Computer:**
   - PATH changes may require a full restart
   - Restart Windows
   - Try again

3. **Check PATH Manually:**
   - Open Command Prompt
   - Type: `echo %PATH%`
   - Look for `C:\ffmpeg\bin` in the output
   - If not there, add it manually (see Method 2, Step 3)

4. **Use Full Path:**
   - Instead of `ffmpeg`, use: `C:\ffmpeg\bin\ffmpeg.exe`
   - If this works, PATH is not set correctly

### Permission Denied

**Problem:** "Access denied" or "Permission denied" errors

**Solution:**
- Run Command Prompt as Administrator
- Right-click Command Prompt → "Run as administrator"
- Try installation again

### Download Fails

**Problem:** download_ffmpeg.bat fails to download

**Solutions:**

1. **Check Internet Connection:**
   - Ensure VM has internet access
   - Try opening https://github.com in browser

2. **Manual Download:**
   - Use browser to download from: https://github.com/BtbN/FFmpeg-Builds/releases
   - Save as `ffmpeg.zip` in the installation folder
   - Run `install_ffmpeg.bat`

3. **Use Alternative Source:**
   - Download from: https://www.gyan.dev/ffmpeg/builds/
   - Get the "release full" build
   - Extract and follow Method 2

### Antivirus Blocking

**Problem:** Antivirus blocks FFmpeg installation

**Solution:**
- Temporarily disable antivirus
- Install FFmpeg
- Re-enable antivirus
- Add `C:\ffmpeg` to antivirus exclusions

## 📋 For Offline Installation

If the VM has no internet access:

1. **On a computer with internet:**
   - Download: https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
   - Save to USB drive

2. **On the VM:**
   - Copy zip file from USB to VM
   - Extract to `C:\ffmpeg`
   - Add to PATH manually (Method 2, Step 3)
   - Verify with `ffmpeg -version`

## 🎯 Quick Reference

### Installation Locations

- **Recommended:** `C:\ffmpeg`
- **Alternative:** `C:\Program Files\ffmpeg`
- **Portable:** Any folder, just add `\bin` to PATH

### Required Files

After installation, you should have:
```
C:\ffmpeg\
├── bin\
│   ├── ffmpeg.exe    (main program)
│   ├── ffprobe.exe   (media info)
│   └── ffplay.exe    (player)
├── doc\
└── presets\
```

### PATH Entry

Add this to system PATH:
```
C:\ffmpeg\bin
```

### Test Commands

```cmd
# Check version
ffmpeg -version

# Check if it can process video
ffmpeg -i test.mp4 -t 1 output.mp4

# Get video info
ffprobe test.mp4
```

## 🆘 Still Having Issues?

### Check Installation Status

Run this diagnostic script:

```cmd
@echo off
echo Checking FFmpeg installation...
echo.
echo 1. Checking if ffmpeg command is available:
where ffmpeg
echo.
echo 2. Checking PATH variable:
echo %PATH% | findstr /i "ffmpeg"
echo.
echo 3. Checking if file exists:
if exist "C:\ffmpeg\bin\ffmpeg.exe" (
    echo Found: C:\ffmpeg\bin\ffmpeg.exe
) else (
    echo NOT FOUND: C:\ffmpeg\bin\ffmpeg.exe
)
echo.
echo 4. Trying to run ffmpeg:
ffmpeg -version
pause
```

Save this as `check_ffmpeg.bat` and run it.

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "command not found" | Not in PATH | Add to PATH or restart |
| "Access denied" | No permissions | Run as Administrator |
| "DLL not found" | Incomplete install | Re-extract all files |
| "Invalid command" | Wrong version | Download correct build |

## 📞 Support

If you still can't install FFmpeg:

1. Check Windows Event Viewer for errors
2. Try running as Administrator
3. Check antivirus logs
4. Verify Windows version compatibility
5. Try portable version (no installation needed)

## ✅ Success Indicators

You'll know FFmpeg is correctly installed when:

- ✅ `ffmpeg -version` shows version info
- ✅ `where ffmpeg` shows path to ffmpeg.exe
- ✅ Video uploads in iDRS get automatically processed
- ✅ No FFmpeg warnings in iDRS logs
- ✅ Video tutorials play smoothly

## 🎬 After Installation

Once FFmpeg is installed:

1. **Restart iDRS server** (if running)
2. **Upload a test video** through admin panel
3. **Check processing status** in admin
4. **Verify video plays** on client PC

The video should:
- Upload quickly
- Process automatically in background
- Show "Completed" status in admin
- Play instantly on client PCs

---

**Remember:** FFmpeg is now **REQUIRED** for iDRS video tutorial features. The application will warn you if it's not installed.
