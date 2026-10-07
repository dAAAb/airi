#!/bin/sh
set -eu
hub_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$hub_dir/.venv/bin/python" -m uvicorn server:app \
  --app-dir "$hub_dir" --host 127.0.0.1 --port 8884 --no-access-log
