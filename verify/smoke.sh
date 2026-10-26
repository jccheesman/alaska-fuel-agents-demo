#!/usr/bin/env bash
# Serve the site locally and run the headless walkthrough.
#   verify/smoke.sh            # uses port 8765
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8765}"
python3 -m http.server "$PORT" -d site --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
sleep 1
du -sh site/data
node verify/screenshot_states.mjs --base "http://127.0.0.1:$PORT" --phone
