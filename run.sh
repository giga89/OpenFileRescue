#!/usr/bin/env bash
# ==============================================================================
# OpenFileRescue - Universal Smart Launcher (Linux & macOS)
# Auto-detects Astral UV -> Python 3 -> Docker
# ==============================================================================
set -e

# Add common local bin paths if present
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

echo "=================================================="
echo " Starting OpenFileRescue..."
echo "=================================================="

# 1. Check for Astral UV (Fastest, zero Python pre-installation needed)
if command -v uv >/dev/null 2>&1; then
    echo " [OK] Using Astral UV (blazing-fast isolated environment)..."
    exec uv run run.py "$@"
fi

# 2. Check for standard Python 3
if command -v python3 >/dev/null 2>&1; then
    echo " [OK] Using system Python 3..."
    exec python3 run.py "$@"
elif command -v python >/dev/null 2>&1; then
    echo " [OK] Using system Python..."
    exec python run.py "$@"
fi

# 3. Check for Docker as containerized fallback
if command -v docker >/dev/null 2>&1; then
    echo " [INFO] Python not found on host. Launching container via Docker Compose..."
    if docker compose version >/dev/null 2>&1; then
        exec docker compose up
    else
        exec docker-compose up
    fi
fi

# 4. If neither UV, Python, nor Docker is installed, offer 1-second UV install
echo ""
echo " [!] No Python, UV, or Docker environment detected."
echo "     The easiest zero-admin way to run OpenFileRescue is with Astral UV."
echo ""
echo "     Install UV instantly with one command (no sudo required):"
echo "     curl -LsSf https://astral.sh/uv/install.sh | sh"
echo ""
echo "     Then run: ./run.sh"
echo "=================================================="
exit 1
