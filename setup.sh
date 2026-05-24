#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "==> Creating virtual environment..."
python3 -m venv .venv

echo "==> Installing Python dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Installing Playwright browsers (Chromium)..."
.venv/bin/playwright install chromium
.venv/bin/playwright install-deps chromium 2>/dev/null || true

echo ""
echo "✓ Setup complete!"
echo ""
echo "To start the app:"
echo "  .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "Then open:  http://localhost:8000"
