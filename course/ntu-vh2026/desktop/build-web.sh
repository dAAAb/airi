#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/../../.." && pwd)
cd "$repo_dir"
export VITE_AIRI_LOCAL_INSTALLER=true
export VITE_AIRI_DISABLE_TOOLS=true
export VITE_SERVER_URL=http://127.0.0.1:17900/_local_api_unavailable
# Some macOS build hosts cannot allocate another tree of filesystem watchers.
export CHOKIDAR_USEPOLLING=true
corepack pnpm --filter @proj-airi/stage-web build
