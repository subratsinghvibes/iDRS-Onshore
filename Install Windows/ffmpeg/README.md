# FFmpeg Package for Windows

## 📦 Package Information

**File:** `ffmpeg-master-latest-win64-gpl.zip`  
**Size:** 206 MB  
**Version:** Latest master build (GPL)  
**Platform:** Windows 64-bit  
**Source:** [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases)

## 🎯 Purpose

This FFmpeg package is **REQUIRED** for the video tutorial feature in IDRS. It enables:

- Automatic video compression (700MB → 180MB)
- Instant video streaming (2-3 seconds load time)
- Smooth, buffer-free playback
- Professional user experience

## 📥 Installation

### Automated Installation (Recommended)

```cmd
cd "Install Windows"
install_ffmpeg.bat (Run as Administrator)
```

This will:
1. Extract FFmpeg from the zip file
2. Install to `C:\ffmpeg`
3. Add to system PATH
4. Verify installation

### Manual Installation

1. Extract `ffmpeg-master-latest-win64-gpl.zip`
2. Copy extracted folder to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to system PATH
4. Restart command prompt
5. Verify: `ffmpeg -version`

## ✅ Verification

After installation, verify FFmpeg is working:

```cmd
ffmpeg -version
```

Should show:
```
ffmpeg version N-xxxxx-gxxxxxxx
built with gcc x.x.x
configuration: --enable-gpl ...
```

## 📊 What's Included

The FFmpeg package contains:

- **ffmpeg.exe** - Video/audio converter and processor
- **ffprobe.exe** - Media file analyzer
- **ffplay.exe** - Media player
- All required codecs (H.264, AAC, etc.)
- GPL-licensed build with full features

## 🔧 Usage in IDRS

FFmpeg is used automatically by IDRS when:

1. **Video Upload:** Admin uploads video through admin panel
2. **Processing:** FFmpeg compresses and optimizes video
3. **Streaming:** Optimized video served to users

No manual FFmpeg commands needed - it's all automatic!

## ⚠️ Important Notes

### Why GPL Build?

We use the GPL build (not LGPL) because it includes:
- All codecs (H.264, H.265, etc.)
- Full encoding capabilities
- Best compression quality
- Maximum compatibility

### File Size

The 206 MB package includes:
- FFmpeg executables (3 files)
- All codec libraries
- Documentation
- License files

After installation to `C:\ffmpeg`, it uses about 300 MB of disk space.

### System Requirements

- Windows 10 or Windows Server 2016 or later
- 64-bit operating system
- 300 MB free disk space
- Administrator access (for installation)

## 🚨 Without FFmpeg

If FFmpeg is not installed:

- ❌ Videos won't compress (stay at 700MB+)
- ❌ Extremely slow loading (10-15 minutes)
- ❌ Constant buffering
- ❌ Poor user experience
- ❌ Video feature essentially unusable

## ✅ With FFmpeg

When FFmpeg is properly installed:

- ✅ Videos compress automatically (74% reduction)
- ✅ Instant loading (2-3 seconds)
- ✅ No buffering
- ✅ Smooth playback
- ✅ Professional experience

## 📚 Additional Information

### License

FFmpeg is licensed under GPL v2 or later. See included LICENSE files in the package.

### Updates

This package is from the latest master build as of the deployment date. FFmpeg is actively developed, but this version is stable and tested with IDRS.

### Support

For FFmpeg-specific issues:
- Official site: https://ffmpeg.org
- Documentation: https://ffmpeg.org/documentation.html
- GitHub: https://github.com/FFmpeg/FFmpeg

For IDRS integration issues:
- See: `FFMPEG_INSTALLATION_GUIDE.md`
- See: `VIDEO_PROCESSING_WORKFLOW.md`
- Check: `logs/django.log`

## 🔍 Troubleshooting

### Installation Fails

**Problem:** Extract or copy fails  
**Solution:** Run as Administrator, check disk space

### FFmpeg Not Found After Install

**Problem:** `ffmpeg -version` doesn't work  
**Solution:** Restart command prompt, verify PATH

### Videos Still Don't Compress

**Problem:** Videos upload but don't process  
**Solution:** 
1. Verify FFmpeg: `ffmpeg -version`
2. Check logs: `type logs\django.log`
3. Restart Django server

## ✅ Verification Checklist

After installation:

- [ ] FFmpeg installed to `C:\ffmpeg`
- [ ] `C:\ffmpeg\bin` in system PATH
- [ ] `ffmpeg -version` works
- [ ] Can see version number
- [ ] Command prompt restarted
- [ ] Django server restarted
- [ ] Video upload test successful
- [ ] Video compression working

---

**Package Date:** February 2026  
**Build:** Latest master (GPL)  
**Platform:** Windows 64-bit  
**Size:** 206 MB (compressed), ~300 MB (installed)
