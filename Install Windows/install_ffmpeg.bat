@echo off
REM ========================================
REM FFmpeg Installation Script for Windows
REM Installs FFmpeg from included package
REM Must be run as Administrator
REM ========================================

echo.
echo ========================================
echo FFmpeg Installation for iDRS
echo ========================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator
    echo Right-click and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [1/5] Checking for existing FFmpeg installation...
where ffmpeg >nul 2>nul
if %errorLevel% equ 0 (
    echo FFmpeg is already installed!
    ffmpeg -version | findstr "ffmpeg version"
    echo.
    echo Do you want to reinstall? (Y/N)
    set /p REINSTALL=
    if /i not "%REINSTALL%"=="Y" (
        echo Keeping existing installation.
        goto :end
    )
)

echo.
echo [2/5] Checking for FFmpeg package...
if not exist "ffmpeg\ffmpeg-master-latest-win64-gpl.zip" (
    echo ERROR: FFmpeg package not found!
    echo.
    echo Expected location: ffmpeg\ffmpeg-master-latest-win64-gpl.zip
    echo.
    echo The FFmpeg package (206 MB) should be included in the installation folder.
    echo If missing, it may not have been copied to the VM.
    echo.
    pause
    exit /b 1
)

echo FFmpeg package found (206 MB)
echo.

echo [3/5] Extracting FFmpeg package...
echo This may take 1-2 minutes...
echo.

REM Create temp directory
set TEMP_DIR=%TEMP%\ffmpeg_install_%RANDOM%
mkdir "%TEMP_DIR%"

REM Extract using PowerShell
powershell -Command "Expand-Archive -Path 'ffmpeg\ffmpeg-master-latest-win64-gpl.zip' -DestinationPath '%TEMP_DIR%' -Force"

if %errorLevel% neq 0 (
    echo ERROR: Failed to extract FFmpeg package
    echo.
    rmdir /s /q "%TEMP_DIR%"
    pause
    exit /b 1
)

echo Extraction complete!
echo.

echo [4/5] Installing FFmpeg to C:\ffmpeg...

REM Find extracted folder
for /d %%i in ("%TEMP_DIR%\ffmpeg-*") do set FFMPEG_EXTRACTED=%%i

if not exist "%FFMPEG_EXTRACTED%\bin\ffmpeg.exe" (
    echo ERROR: FFmpeg executable not found in extracted files
    echo.
    rmdir /s /q "%TEMP_DIR%"
    pause
    exit /b 1
)

REM Remove old installation
if exist "C:\ffmpeg" (
    echo Removing old installation...
    rmdir /s /q "C:\ffmpeg"
)

REM Copy to C:\ffmpeg
xcopy /E /I /Y "%FFMPEG_EXTRACTED%\*" "C:\ffmpeg\" >nul

if %errorLevel% neq 0 (
    echo ERROR: Failed to copy FFmpeg to C:\ffmpeg
    echo.
    rmdir /s /q "%TEMP_DIR%"
    pause
    exit /b 1
)

echo FFmpeg installed to C:\ffmpeg
echo.

REM Cleanup temp files
rmdir /s /q "%TEMP_DIR%"

echo [5/5] Adding FFmpeg to system PATH...

REM Get current PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set CURRENT_PATH=%%b

REM Check if already in PATH
echo %CURRENT_PATH% | find /i "C:\ffmpeg\bin" >nul
if %errorLevel% equ 0 (
    echo FFmpeg is already in system PATH
) else (
    REM Add to PATH
    setx /M PATH "%CURRENT_PATH%;C:\ffmpeg\bin" >nul 2>&1
    if %errorLevel% equ 0 (
        echo FFmpeg added to system PATH successfully!
    ) else (
        echo Warning: Could not add to system PATH automatically.
        echo Please add manually: C:\ffmpeg\bin
    )
)

REM Add to current session PATH
set PATH=%PATH%;C:\ffmpeg\bin

echo.
echo ========================================
echo FFmpeg Installation Complete!
echo ========================================
echo.
echo Installation location: C:\ffmpeg
echo Binaries location: C:\ffmpeg\bin
echo.
echo Verifying installation...
C:\ffmpeg\bin\ffmpeg.exe -version | findstr "ffmpeg version"
echo.
echo SUCCESS: FFmpeg is installed and working!
echo.
echo IMPORTANT: Please restart your command prompt
echo for the PATH changes to take effect everywhere.
echo.

:end
pause
