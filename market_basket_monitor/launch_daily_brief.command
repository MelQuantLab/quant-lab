#!/bin/bash

# One-click macOS launcher for the live MelQuantLabs Daily News Brief.
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
REPORT_PATH="$APP_DIR/daily_ftse_digest.html"

show_error() {
    osascript -e 'display alert "Daily brief could not be created" message "Check the launcher window for details, then try again while connected to the internet." as critical'
}
trap show_error ERR

cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    osascript -e 'display alert "Python 3 is required" message "Install Python 3, then open the daily brief again." as critical'
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "First-time setup: preparing the daily news brief..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    "$VENV_DIR/bin/python" -m pip install --quiet -r requirements.txt
fi

echo "Building today's MelQuantLabs market brief..."
echo "This can take a few minutes while live market and news data are collected."
"$VENV_DIR/bin/python" daily_ftse_digest.py --dry-run

open "$REPORT_PATH"
osascript -e 'display notification "Today’s market brief is ready." with title "MelQuantLabs"'
echo "Done. The daily brief has opened in your browser."
