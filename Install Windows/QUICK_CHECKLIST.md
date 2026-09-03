# Quick Installation Checklist

## ⚡ 5-Minute Setup

### ✅ Pre-Installation
- [ ] Python 3.13.9 installed
- [ ] Administrator access available
- [ ] 10+ GB free disk space

### ✅ Step 1: FFmpeg (CRITICAL)
```cmd
download_ffmpeg.bat
install_ffmpeg.bat (Run as Admin)
ffmpeg -version (Verify)
```

### ✅ Step 2: Install Packages
```cmd
install_offline_simple.bat
```

### ✅ Step 3: Setup Database
```cmd
setup_windows.bat
```

### ✅ Step 4: Start Server
```cmd
start_server.bat
```

### ✅ Step 5: Verify
- [ ] Open http://localhost:8022
- [ ] Login to admin panel
- [ ] Upload test video
- [ ] Check video processes
- [ ] Test video playback

## 🚨 Critical Requirements

### FFmpeg is MANDATORY
- ❌ Without FFmpeg: Videos won't compress (700MB stays 700MB)
- ❌ Without FFmpeg: 10-15 minute load times
- ✅ With FFmpeg: Videos compress to 150-250MB
- ✅ With FFmpeg: 2-3 second load times

### Verification Commands
```cmd
# Check Python
python --version

# Check FFmpeg
ffmpeg -version

# Check packages
.venv\Scripts\activate
pip list

# Check Django
python manage.py check
```

## 🔧 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Python not found | Install Python 3.13.9, check "Add to PATH" |
| FFmpeg not found | Run install_ffmpeg.bat as Admin |
| Packages fail | Check offline_packages folder exists |
| Server won't start | Check port 8022 not in use |
| Videos don't compress | Verify FFmpeg: `ffmpeg -version` |

## 📞 Need Help?

1. Check `README_INSTALLATION.md` for detailed guide
2. Check `FFMPEG_INSTALLATION_GUIDE.md` for FFmpeg help
3. Check `logs\django.log` for errors
4. Run `verify_ffmpeg.bat` to test FFmpeg

## ✅ Success Criteria

You're done when:
- ✅ Server starts without errors
- ✅ Can access http://localhost:8022
- ✅ Videos upload and compress automatically
- ✅ Videos play instantly (2-3 seconds)
- ✅ No errors in browser console

---

**Total Time:** 5-10 minutes (plus video processing time)
