#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec .venv/bin/python kaedetai/serve-taigi.py
