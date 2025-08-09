#!/usr/bin/env bash
set -e

echo "🔄 Installerar Python-paket..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🌐 Installerar Chromium för Playwright..."
python -m playwright install --with-deps chromium
