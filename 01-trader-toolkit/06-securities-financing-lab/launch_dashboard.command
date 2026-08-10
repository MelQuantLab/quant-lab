#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_DIR="$PROJECT_DIR/.venv"

cd "$PROJECT_DIR"

if [ ! -x "$ENV_DIR/bin/python" ]; then
  echo "Preparing the Securities Financing Lab for first use..."
  python3 -m venv "$ENV_DIR"
  "$ENV_DIR/bin/python" -m pip install --upgrade pip
  "$ENV_DIR/bin/python" -m pip install -r requirements.txt
fi

echo "Opening the Equity Borrow & Financing Scenario Lab..."
echo "Keep this window open while using the dashboard."

(sleep 2; open "http://127.0.0.1:8501") &
exec "$ENV_DIR/bin/python" -m streamlit run app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true
