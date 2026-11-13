#!/bin/bash
# 仅启动本机页面（连已在线的 GPU）。
# 完整一键（GPU + TURN + 抠图 + HTTPS 页面）请用: scripts/up-xiaoxin.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${MOSS_PORT:-8000}"
APP="$ROOT/fine-digital-human"

live_gpu_url() {
  local host suffix
  host="$(tailscale status | awk '$2 ~ /^colab-livetalking/ && $0 !~ /offline/ { print $2; exit }')"
  if [ -z "$host" ]; then
    return 1
  fi
  suffix="$(tailscale status --json | python3 -c 'import json,sys; name=json.load(sys.stdin)["Self"]["DNSName"].rstrip("."); print(name.split(".",1)[1])')"
  printf 'http://%s.%s:8010' "$host" "$suffix"
}

gpu_code() {
  local url
  url="$(live_gpu_url 2>/dev/null || true)"
  if [ -z "$url" ]; then
    echo "000"
    return
  fi
  curl -sS -m 8 -o /dev/null -w "%{http_code}" "${url}/" || echo "000"
}

point_env_to_live_gpu() {
  local url envf
  url="$(live_gpu_url)" || return 0
  envf="$APP/.env"
  [ -f "$envf" ] || return 0
  python3 - "$envf" "$url" << 'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
url = sys.argv[2]
line = f"LIVETALKING_URL={url}"
lines = path.read_text(encoding="utf-8").splitlines()
out, hit = [], False
for row in lines:
    if row.startswith("LIVETALKING_URL="):
        out.append(line)
        hit = True
    else:
        out.append(row)
if not hit:
    out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(line)
PY
}

echo "=== 语音唤醒版 · 小信 ==="
code="$(gpu_code)"
if [ "$code" = "000" ]; then
  echo "LiveTalking 不在线，先启动 GPU"
  "$ROOT/scripts/run-and-check.sh" gpu
else
  echo "LiveTalking 已在线  HTTP $code"
fi
point_env_to_live_gpu

if ! grep -q '^WAKE_ENABLED=' "$APP/.env"; then
  printf '\nWAKE_ENABLED=true\n' >>"$APP/.env"
else
  python3 - "$APP/.env" << 'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
out = [("WAKE_ENABLED=true" if line.startswith("WAKE_ENABLED=") else line) for line in lines]
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
fi

pid="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
if [ -n "$pid" ]; then
  kill "$pid" >/dev/null 2>&1 || true
  sleep 0.4
fi

cd "$APP"
# macOS 没有 setsid。nohup 让用户在终端里启动后，关掉终端也不会带走进程。
TURN_ENV="${TURN_ENV_FILE:-$ROOT/.secrets/turn.env}"
if [ -f "$TURN_ENV" ]; then
  export TURN_ENV_FILE="$TURN_ENV"
fi
WAKE_ENABLED=true nohup env ${TURN_ENV_FILE:+TURN_ENV_FILE="$TURN_ENV_FILE"} WAKE_ENABLED=true \
  .venv/bin/python3.12 -m uvicorn app:app --host 127.0.0.1 --port "$PORT" \
  >"local-${PORT}.log" 2>&1 < /dev/null &
echo $! >"local-${PORT}.pid"
disown || true

for _ in $(seq 1 20); do
  curl -sf -m 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 && break
  sleep 0.5
done

echo "=== 配置 ==="
curl -sS -m 5 "http://127.0.0.1:${PORT}/api/avatar-config"
echo
echo "页面： http://127.0.0.1:${PORT}/"
echo "用 Chrome 打开，允许麦克风，直接说话。说话会打断当前回答"
