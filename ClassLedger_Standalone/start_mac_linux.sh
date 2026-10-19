#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python setup_admin.py --ensure
exec .venv/bin/python launch.py
