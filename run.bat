@echo off
cd /d "%~dp0"

echo ===================================================
echo   App Launcher (Windows / Python-only Environment)
echo ===================================================
echo.

:: 1. Auto-detect Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python and ensure it is added to your environment variables.
    echo.
    pause
    exit /b 1
)

:: 2. Bootstrap 'uv' via Python pip if missing
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] 'uv' package manager not found. Bootstrapping via pip...
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install uv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install 'uv'.
        echo.
        pause
        exit /b 1
    )
    echo [INFO] 'uv' installed successfully.
)

:: 3. Auto-detect Python entry point
set "ENTRY_POINT="
if exist "app.py" set "ENTRY_POINT=app.py"
if not defined ENTRY_POINT (if exist "main.py" set "ENTRY_POINT=main.py")
if not defined ENTRY_POINT (if exist "src\app.py" set "ENTRY_POINT=src\app.py")

if not defined ENTRY_POINT (
    echo [ERROR] Python entry point ^(app.py / main.py / src\app.py^) not found.
    echo.
    pause
    exit /b 1
)

:: 4. Auto-create .venv and sync package dependencies
if not exist ".venv" (
    echo [INFO] Creating virtual environment...
    uv venv
)

if exist "pyproject.toml" (
    echo [INFO] Syncing dependencies...
    uv sync
)

:: 5. Launch Application
echo.
echo [INFO] Launching %ENTRY_POINT% ...
echo.

uv run streamlit run "%ENTRY_POINT%"

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Application stopped or encountered an error.
)

echo.
pause
