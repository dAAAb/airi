#!/bin/sh
# Run Vite directly: the upstream dev script includes an unqualified --host.
set -eu
course_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$course_dir/../.." && pwd)
cd "$repo_dir"
exec pnpm -F @proj-airi/stage-web exec vite --host 127.0.0.1 --port 5174 --strictPort
