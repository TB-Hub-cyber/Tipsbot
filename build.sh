#!/usr/bin/env bash
set -eux
pip install -r requirements.txt
python -m playwright install --with-deps chromium
