#!/usr/bin/env bash
# 로컬 개발: Flask(127.0.0.1:5181) + Vite(0.0.0.0:5180). 폰은 같은 와이파이에서 접속.
# 포트가 이미 쓰이고 있으면 다른 번호로 옮기지 않고 실패한다(strictPort) — 다른 프로젝트 화면이 뜨는 혼동 방지.
set -euo pipefail
cd "$(dirname "$0")"

(cd backend && .venv/bin/flask --app app db upgrade && exec .venv/bin/flask --app app run --port 5181 --debug) &
trap 'kill 0' EXIT

IP=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || echo localhost)
echo ""
echo "📱 폰(같은 와이파이)에서 열기: http://$IP:5180"
echo ""
cd frontend && npm run dev -- --host 0.0.0.0
