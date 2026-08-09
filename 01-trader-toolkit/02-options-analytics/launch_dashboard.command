#!/bin/bash

# One-click macOS launcher for the MelQuantLabs Options Dashboard.
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
URL="http://127.0.0.1:8501"

cd "$APP_DIR"

if curl --silent --fail "$URL/_stcore/health" >/dev/null 2>&1; then
    open "$URL"
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    osascript -e 'display alert "Python 3 is required" message "Install Python 3, then open the dashboard again." as critical'
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/streamlit" ]; then
    echo "First-time setup: preparing the dashboard..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt
fi

(sleep 2 && open "$URL") &
echo "MelQuantLabs Options Dashboard is starting."
echo "Keep this window open while you use the dashboard."
echo "Close this window or press Control-C to stop it."

exec "$VENV_DIR/bin/streamlit" run app.py \
    --server.address 127.0.0.1 \
    --server.port 8501 \
    --server.headless true
