#!/bin/bash
# 从本机把 LiveTalking 拉到当前在线的 Colab GPU 上。
# 权重在 GPU 下载，不从本机拷贝。
#
# 用法:
#   scripts/run-and-check.sh gpu     同步代码并启动 LiveTalking
#   scripts/run-and-check.sh up      gpu，并重启本机 dh-admin 与 fine-digital-human
#   scripts/run-and-check.sh check   只检查连通
#
# 指定节点: GPU_HOST=colab-livetalking-1.YOUR-HOST.ts.net scripts/run-and-check.sh gpu
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GPU_REPO="${GPU_REPO:-/content/livetalking/LiveTalking}"
MOSS_PORT="${MOSS_PORT:-8000}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)

resolve_gpu_host() {
  if [ -n "${GPU_HOST:-}" ]; then
    printf '%s\n' "$GPU_HOST"
    return
  fi
  local name suffix
  name="$(tailscale status | awk '$2 ~ /^colab-livetalking/ && $0 !~ /offline/ { print $2; exit }')"
  if [ -z "$name" ]; then
    echo "没有在线的 colab-livetalking 节点。先在 Colab 跑 colab_google_gpu_bootstrap.py。" >&2
    exit 1
  fi
  suffix="$(tailscale status --json | python3 -c 'import json,sys; name=json.load(sys.stdin)["Self"]["DNSName"].rstrip("."); print(name.split(".",1)[1])')"
  printf '%s.%s\n' "$name" "$suffix"
}

GPU_HOST="$(resolve_gpu_host)"
SSH=(ssh "${SSH_OPTS[@]}" "root@${GPU_HOST}")

# Colab 换机后同名 MagicDNS 主机密钥会变
ssh-keygen -R "$GPU_HOST" >/dev/null 2>&1 || true

check() {
  local name="$1" url="$2"
  local code
  code="$(curl -sS -m 8 -o /dev/null -w "%{http_code}" "$url" || echo "000")"
  if [ "$code" = "000" ]; then
    echo "FAIL  $name  $url"
    return 1
  fi
  echo "OK    $name  $url  HTTP $code"
}

ensure_remote_rsync() {
  if "${SSH[@]}" "command -v rsync >/dev/null 2>&1"; then
    return 0
  fi
  echo "=== 远端没有 rsync，正在用 apt 安装 ==="
  "${SSH[@]}" "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null"
}

sync_code() {
  echo "=== 同步代码到 ${GPU_HOST}（跳过模型、密钥和本地虚拟环境）==="
  "${SSH[@]}" "mkdir -p '$GPU_REPO'"
  ensure_remote_rsync
  rsync -az --delete \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.venv/' \
    --exclude 'node_modules/' \
    --exclude '__pycache__/' \
    --exclude '*.ipynb' \
    --exclude '/models/' \
    --exclude 's3fd.pth' \
    --exclude 'data/' \
    --exclude 'assets/avatars/' \
    --exclude 'dh-admin/' \
    --exclude 'fine-digital-human/' \
    -e "ssh ${SSH_OPTS[*]}" \
    "$ROOT/" "root@${GPU_HOST}:${GPU_REPO}/"
}

start_gpu() {
  echo "=== 在 GPU 上下载模型并启动 LiveTalking ==="
  "${SSH[@]}" "bash '$GPU_REPO/scripts/gpu-livetalking.sh' all"
}

restart_local() {
  echo "=== 重建 dh-admin 容器 ==="
  docker compose -f "$ROOT/dh-admin/docker-compose.yml" --project-directory "$ROOT/dh-admin" up -d --force-recreate

  echo "=== 重启 fine-digital-human :$MOSS_PORT ==="
  local pid
  pid="$(lsof -nP -iTCP:"$MOSS_PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [ -n "$pid" ]; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 0.4
  fi
  cd "$ROOT/fine-digital-human"
  nohup .venv/bin/python3.12 -m uvicorn app:app --host 127.0.0.1 --port "$MOSS_PORT" \
    >"local-${MOSS_PORT}.log" 2>&1 &
  echo $! >"local-${MOSS_PORT}.pid"
  disown || true
  cd "$ROOT"
  for _ in $(seq 1 20); do
    curl -sf -m 2 "http://127.0.0.1:${MOSS_PORT}/" >/dev/null 2>&1 && break
    sleep 0.5
  done
}

run_checks() {
  echo "=== 检查 ${GPU_HOST} ==="
  local failed=0
  "${SSH[@]}" "nvidia-smi -L && tailscale ip -4" || failed=1
  check "LiveTalking" "http://${GPU_HOST}:8010/" || failed=1
  check "dh-admin" "http://127.0.0.1:18200/api/health" || failed=1
  check "fine-digital-human" "http://127.0.0.1:${MOSS_PORT}/" || failed=1
  check "形象配置" "http://127.0.0.1:${MOSS_PORT}/api/avatar-config" || failed=1
  if [ "$failed" -ne 0 ]; then
    echo "有检查未通过。GPU 日志：ssh root@${GPU_HOST} tail -n 80 /tmp/livetalking_app.log"
    exit 1
  fi
  echo "页面： http://127.0.0.1:${MOSS_PORT}/"
}

case "${1:-gpu}" in
  gpu)
    sync_code
    start_gpu
    check "LiveTalking" "http://${GPU_HOST}:8010/"
    ;;
  up)
    sync_code
    start_gpu
    restart_local
    run_checks
    ;;
  check)
    run_checks
    ;;
  *)
    echo "用法: $0 [gpu|up|check]" >&2
    exit 2
    ;;
esac
