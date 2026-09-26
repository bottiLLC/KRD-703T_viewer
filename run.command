#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "==================================================="
echo "  App Launcher (Mac/Linux / Python-only Env)"
echo "==================================================="
echo ""

# 1. Auto-detect Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python is not installed or not in PATH."
    read -p "Press [Enter] key to exit..."
    exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

# 2. Bootstrap 'uv' via Python pip if missing
if ! command -v uv &> /dev/null; then
    echo "[INFO] 'uv' package manager not found. Bootstrapping via pip..."
    $PYTHON_CMD -m pip install --upgrade pip >/dev/null 2>&1
    $PYTHON_CMD -m pip install uv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install 'uv'."
        read -p "Press [Enter] key to exit..."
        exit 1
    fi
    echo "[INFO] 'uv' installed successfully."
fi

# Ensure local bin is in PATH for Mac/Linux just in case pip installed it there
export PATH="$HOME/.local/bin:$PATH"

# 3. Auto-detect Python entry point
ENTRY_POINT=""
for file in app.py main.py src/app.py; do
    if [ -f "$file" ]; then
        ENTRY_POINT="$file"
        break
    fi
done

if [ -z "$ENTRY_POINT" ]; then
    echo "[ERROR] Python entry point (app.py / main.py / src/app.py) not found."
    read -p "Press [Enter] key to exit..."
    exit 1
fi

# 4. Auto-create .venv and sync package dependencies
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment..."
    uv venv
fi

if [ -f "pyproject.toml" ]; then
    echo "[INFO] Syncing dependencies..."
    uv sync
fi

# 5. Launch Application
echo ""
echo "[INFO] Launching $ENTRY_POINT ..."
echo ""

uv run streamlit run "$ENTRY_POINT"

if [ $? -ne 0 ]; then
    echo ""
    echo "[WARNING] Application stopped or encountered an error."
fi

echo ""
read -p "Press [Enter] key to exit..."
