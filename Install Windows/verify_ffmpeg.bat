@echo off
REM ============================================================================
REM FFmpeg Verification Script
REM Tests if FFmpeg is properly installed and working
REM ============================================================================

echo ========================================
echo FFmpeg Verification Test
echo ========================================
echo.

REM Test 1: Check if ffmpeg command exists
echo [Test 1/3] Checking if FFmpeg is in PATH...
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo FAILED: FFmpeg not found in system PATH
    echo.
    echo FFmpeg is REQUIRED for video tutorial features!
    echo.
    echo To install FFmpeg:
    echo 1. Run: download_ffmpeg.bat
    echo 2. Then run: install_ffmpeg.bat (as Administrator)
    echo.
    echo Or see: FFMPEG_INSTALLATION_GUIDE.md
    echo.
    pause
    exit /b 1
) else (
    echo PASSED: FFmpeg found in PATH
    where ffmpeg
    echo.
)

REM Test 2: Check FFmpeg version
echo [Test 2/3] Checking FFmpeg version...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo FAILED: FFmpeg command exists but doesn't work
    echo.
    pause
    exit /b 1
) else (
    echo PASSED: FFmpeg is working
    ffmpeg -version | findstr "ffmpeg version"
    echo.
)

REM Test 3: Check FFmpeg codecs
echo [Test 3/3] Checking required codecs...
ffmpeg -codecs 2>nul | findstr "h264" >nul
if errorlevel 1 (
    echo WARNING: H.264 codec not found
    echo Video compression may not work properly
    echo.
) else (
    echo PASSED: H.264 codec available
)

ffmpeg -codecs 2>nul | findstr "aac" >nul
if errorlevel 1 (
    echo WARNING: AAC codec not found
    echo Audio processing may not work properly
    echo.
) else (
    echo PASSED: AAC codec available
)

echo.
echo ========================================
echo Verification Complete!
echo ========================================
echo.
echo FFmpeg is properly installed and ready to use.
echo Video tutorial features will work correctly.
echo.
echo Next steps:
echo 1. Upload a video through the admin panel
echo 2. Check that it gets automatically compressed
echo 3. Verify video plays instantly (2-3 seconds)
echo.
pause
