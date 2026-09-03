@echo off
REM ============================================================================
REM FFmpeg Download Information
REM ============================================================================

echo ========================================
echo FFmpeg Package Information
echo ========================================
echo.

REM Check if FFmpeg package already exists
if exist "ffmpeg\ffmpeg-master-latest-win64-gpl.zip" (
    echo ✅ FFmpeg package is ALREADY INCLUDED!
    echo.
    echo Location: ffmpeg\ffmpeg-master-latest-win64-gpl.zip
    echo Size: 206 MB
    echo.
    echo You do NOT need to download anything.
    echo.
    echo To install FFmpeg, run:
    echo   install_ffmpeg.bat (as Administrator)
    echo.
    pause
    exit /b 0
)

echo ❌ FFmpeg package NOT found!
echo.
echo Expected location: ffmpeg\ffmpeg-master-latest-win64-gpl.zip
echo.
echo The FFmpeg package should be included in the installation folder.
echo If you're seeing this message, the package may not have been copied to the VM.
echo.
echo ========================================
echo Manual Download Instructions
echo ========================================
echo.
echo If you need to download FFmpeg manually:
echo.
echo 1. Go to: https://github.com/BtbN/FFmpeg-Builds/releases
echo.
echo 2. Download: ffmpeg-master-latest-win64-gpl.zip
echo    (Look for "latest" release, download the win64-gpl.zip file)
echo.
echo 3. Save to: Install Windows\ffmpeg\
echo    (Create the ffmpeg folder if it doesn't exist)
echo.
echo 4. Run: install_ffmpeg.bat (as Administrator)
echo.
echo ========================================
echo Automated Download (Requires Internet)
echo ========================================
echo.
echo If this VM has internet access, we can download it now.
echo.
set /p DOWNLOAD="Download FFmpeg now? (Y/N): "

if /i not "%DOWNLOAD%"=="Y" (
    echo.
    echo Download cancelled.
    echo Please download manually using the instructions above.
    echo.
    pause
    exit /b 0
)

echo.
echo Downloading FFmpeg (206 MB)...
echo This will take 2-5 minutes depending on your connection...
echo.

REM Create ffmpeg folder if it doesn't exist
if not exist "ffmpeg" mkdir "ffmpeg"

REM Download using PowerShell
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg\ffmpeg-master-latest-win64-gpl.zip' -UseBasicParsing}"

if %errorLevel% neq 0 (
    echo.
    echo ERROR: Download failed!
    echo.
    echo Please download manually:
    echo 1. Go to: https://github.com/BtbN/FFmpeg-Builds/releases
    echo 2. Download: ffmpeg-master-latest-win64-gpl.zip
    echo 3. Save to: Install Windows\ffmpeg\
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Download Complete!
echo ========================================
echo.
echo FFmpeg package downloaded successfully!
echo Location: ffmpeg\ffmpeg-master-latest-win64-gpl.zip
echo Size: 206 MB
echo.
echo Next step: Run install_ffmpeg.bat (as Administrator)
echo.
pause
