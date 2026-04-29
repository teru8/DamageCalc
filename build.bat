@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "SPEC_FILE=%~dp0build.spec"
set "DIST_DIR=%~dp0dist"
set "WORK_DIR=%~dp0.pyinstaller\work"

echo ===================================
echo  PokeDamageCalc EXE build start
echo ===================================
echo.
echo [INFO] Python  : %PYTHON_EXE%
echo [INFO] Output  : dist\PokeDamageCalc\
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

echo.
echo ===================================
echo  Build completed successfully!
echo ===================================
echo.
echo  Run: dist\PokeDamageCalc\PokeDamageCalc.exe
echo.
echo  NOTE: Keep the "_internal" folder next to the EXE.
echo  NOTE: EasyOCR models (~170MB) are downloaded on first launch.
echo.
pause
