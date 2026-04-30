@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "SPEC_FILE=%~dp0build.spec"
set "DIST_DIR=%~dp0dist"
set "WORK_DIR=%~dp0.pyinstaller\work"

echo ===================================
echo  DamageCalc EXE build start
echo ===================================
echo.
echo [INFO] Python  : %PYTHON_EXE%
echo [INFO] Output  : dist\^<app-folder^>\
echo [INFO] Work dir: .pyinstaller\work
echo.

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    "%PYTHON_EXE%" -m pip install "pyinstaller>=6.0"
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

set "CLEAN_FLAG="
if /i "%1"=="clean" set "CLEAN_FLAG=--clean"
if "%CLEAN_FLAG%"=="" (
    echo [INFO] Building executable... (incremental / cache reuse)
) else (
    echo [INFO] Building executable... (full clean build)
)

"%PYTHON_EXE%" -m PyInstaller "%SPEC_FILE%" ^
    --noconfirm ^
    %CLEAN_FLAG% ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    --log-level WARN

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Re-run with --log-level DEBUG for details.
    pause
    exit /b 1
)

set "APP_DIST_DIR="
for /f "delims=" %%D in ('dir /b /ad "%DIST_DIR%"') do (
    if exist "%DIST_DIR%\%%D\*.exe" (
        set "APP_DIST_DIR=%DIST_DIR%\%%D"
        goto :dist_found
    )
)
:dist_found
if "%APP_DIST_DIR%"=="" set "APP_DIST_DIR=%DIST_DIR%"

echo [INFO] Copying README/usage JSON next to EXE...
if exist "%~dp0README.md" (
    copy /Y "%~dp0README.md" "%APP_DIST_DIR%\README.md" >nul
)
for %%F in ("%~dp0usage_data_*.json") do (
    if exist "%%~fF" copy /Y "%%~fF" "%APP_DIST_DIR%\" >nul
)
for %%F in ("%~dp0src\usage_data_*.json") do (
    if exist "%%~fF" copy /Y "%%~fF" "%APP_DIST_DIR%\" >nul
)

echo.
echo ===================================
echo  Build completed successfully!
echo ===================================
echo.
echo  Run: %APP_DIST_DIR%\DamageCalc.exe
echo.
echo  NOTE: Keep the "_internal" folder next to the EXE.
echo  NOTE: EasyOCR models (~170MB) are downloaded on first launch.
echo.
pause
