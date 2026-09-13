#!/usr/bin/env bash
# 로컬 개발: Flask(127.0.0.1:5000) + Vite(0.0.0.0:5173). 폰은 같은 와이파이에서 접속.
set -euo pipefail
cd "$(dirname "$0")"

(cd backend && .venv/bin/flask --app app db upgrade && exec .venv/bin/flask --app app run --port 5000 --debug) &
trap 'kill 0' EXIT

IP=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || echo localhost)
echo ""
echo "📱 폰(같은 와이파이)에서 열기: http://$IP:5173"
echo ""
cd frontend && npm run dev -- --host 0.0.0.0
