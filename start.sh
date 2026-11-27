#!/bin/sh
set -eu
cd /app/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 &
ready=0
i=0
while [ "$i" -lt 30 ]; do
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)" >/dev/null 2>&1; then
    ready=1
    break
  fi
  i=$((i + 1))
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "backend did not open /health" >&2
  exit 1
fi
cd /app/frontend
export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8765}"
exec npx next start -H 0.0.0.0 -p "${PORT:-43123}"
