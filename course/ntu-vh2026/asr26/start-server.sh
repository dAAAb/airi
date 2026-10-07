#!/bin/sh
set -eu
service_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$service_dir"
exec .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8001 --workers 1
