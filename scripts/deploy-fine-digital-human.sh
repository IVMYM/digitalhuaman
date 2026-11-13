#!/bin/bash
# 把 fine-digital-human 部署到当前在线的 Colab。
# LiveTalking 仍由 gpu-livetalking.sh 启动。页面在同一台机器上访问 127.0.0.1:8010。
#
# 用法: scripts/deploy-fine-digital-human.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/fine-digital-human"
REMOTE_APP="${REMOTE_APP:-/content/livetalking/fine-digital-human}"
PORT="${PAGE_PORT:-8000}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)

resolve_gpu_host() {
  if [ -n "${GPU_HOST:-}" ]; then
    printf '%s\n' "$GPU_HOST"
    return
  fi
  local name suffix
  name="$(tailscale status | awk '$2 ~ /^colab-livetalking/ && $0 !~ /offline/ { print $2; exit }')"
  if [ -z "$name" ]; then
    echo "没有在线的 colab-livetalking 节点。" >&2
    exit 1
  fi
  suffix="$(tailscale status --json | python3 -c 'import json,sys; name=json.load(sys.stdin)["Self"]["DNSName"].rstrip("."); print(name.split(".",1)[1])')"
  printf '%s.%s\n' "$name" "$suffix"
}

GPU_HOST="$(resolve_gpu_host)"
SSH=(ssh "${SSH_OPTS[@]}" "root@${GPU_HOST}")

# Colab 换机后同名 MagicDNS 主机密钥会变
ssh-keygen -R "$GPU_HOST" >/dev/null 2>&1 || true

if [ ! -f "$APP/.env" ]; then
  echo "缺少 $APP/.env" >&2
  exit 1
fi

echo "=== 同步 fine-digital-human 到 ${GPU_HOST} ==="
"${SSH[@]}" "mkdir -p '$REMOTE_APP'"
if ! "${SSH[@]}" "command -v rsync >/dev/null 2>&1"; then
  echo "=== 远端没有 rsync，正在用 apt 安装 ==="
  "${SSH[@]}" "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null"
fi
# 页面只读 index.html 和 backgrounds/zhengxin.png。
# static/vendor 是未引用的 MediaPipe（约 34MB），本地脚本也不在 GPU 上跑。
rsync -az --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude '*.log' \
  --exclude '*.pid' \
  --exclude 'static/vendor/' \
  --exclude 'static/backgrounds/nasa-orion.png' \
  --exclude 'test_dsh_session.py' \
  --exclude 'local_avatar.py' \
  --exclude 'start-local.sh' \
  --exclude 'local-requirements.txt' \
  -e "ssh ${SSH_OPTS[*]}" \
  "$APP/" "root@${GPU_HOST}:${REMOTE_APP}/"

echo "=== 写入运行配置（LiveTalking 走本机 8010）==="
tmp="$(mktemp)"
python3 - "$APP/.env" "$tmp" << 'PY'
import pathlib, sys
src, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
lines = src.read_text(encoding="utf-8").splitlines()
out = []
seen_url = False
for line in lines:
    if line.startswith("LIVETALKING_URL="):
        out.append("LIVETALKING_URL=http://127.0.0.1:8010")
        seen_url = True
    elif line.startswith("DH_ADMIN_BASE_URL="):
        continue
    else:
        out.append(line)
if not seen_url:
    out.append("LIVETALKING_URL=http://127.0.0.1:8010")
dest.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
scp "${SSH_OPTS[@]}" "$tmp" "root@${GPU_HOST}:${REMOTE_APP}/.env" >/dev/null
rm -f "$tmp"

echo "=== 安装依赖并启动 :${PORT} ==="
"${SSH[@]}" "bash -s" -- "$REMOTE_APP" "$PORT" << 'EOF'
set -euo pipefail
app="$1"
port="$2"
cd "$app"
wheelhouse="${LIVETALKING_WHEELHOUSE:-/mnt/workspace/livetalking/wheels/pip}"
if compgen -G "$wheelhouse/*.whl" >/dev/null 2>&1 \
  && python3 -m pip install -q --no-index --find-links "$wheelhouse" -r requirements.txt; then
  :
else
  python3 -m pip install -q -r requirements.txt
fi
pid_file=/tmp/fine-digital-human.pid
if [ -f "$pid_file" ]; then
  old="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    kill "$old" 2>/dev/null || true
    sleep 0.4
  fi
  rm -f "$pid_file"
fi
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${port}/tcp" >/dev/null 2>&1 || true
fi
cert_dir=/content/livetalking/certs
mkdir -p "$cert_dir"
dns="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
# Colab 换机后 ACME 偶发 404，重试几次；已有证书则沿用。
ok_cert=0
for _ in $(seq 1 5); do
  if [ -s "$cert_dir/page.crt" ] && [ -s "$cert_dir/page.key" ]; then
    ok_cert=1
    break
  fi
  if tailscale cert --cert-file "$cert_dir/page.crt" --key-file "$cert_dir/page.key" "$dns"; then
    ok_cert=1
    break
  fi
  sleep 3
done
if [ "$ok_cert" != 1 ]; then
  echo "tailscale cert 失败：$dns" >&2
  exit 1
fi
chmod 600 "$cert_dir/page.key" 2>/dev/null || true
tailscale serve --https=443 off >/dev/null 2>&1 || true
nohup python3 -m uvicorn app:app --host 0.0.0.0 --port "$port" \
  --ssl-certfile "$cert_dir/page.crt" \
  --ssl-keyfile "$cert_dir/page.key" \
  >/tmp/fine-digital-human.log 2>&1 &
echo $! >"$pid_file"
for _ in $(seq 1 30); do
  if python3 -c "import urllib.request,ssl; urllib.request.urlopen('https://127.0.0.1:${port}/', timeout=2, context=ssl._create_unverified_context())" >/dev/null 2>&1; then
    echo "fine-digital-human 已用 HTTPS 监听 ${port}"
    exit 0
  fi
  if ! kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "进程已退出，日志末尾：" >&2
    tail -n 40 /tmp/fine-digital-human.log >&2 || true
    exit 1
  fi
  sleep 0.5
done
echo "端口未就绪，日志末尾：" >&2
tail -n 40 /tmp/fine-digital-human.log >&2 || true
exit 1
EOF

code="$(curl -sS -m 15 -o /dev/null -w "%{http_code}" "https://${GPU_HOST}:${PORT}/" || echo "000")"
cfg="$(curl -sS -m 8 "https://${GPU_HOST}:${PORT}/api/avatar-config" || true)"
cfg_safe="$(printf '%s' "$cfg" | python3 -c 'import json,sys
raw=sys.stdin.read().strip()
try:
 d=json.loads(raw)
except Exception:
 print(raw); raise SystemExit
for s in d.get("ice_servers") or []:
  if s.get("credential"): s["credential"]="set"
print(json.dumps(d, ensure_ascii=False))')"
echo "OK    页面  https://${GPU_HOST}:${PORT}/  HTTP ${code}"
echo "配置  ${cfg_safe}"
if [ "$code" = "000" ]; then
  echo "本机访问失败。GPU 日志：ssh root@${GPU_HOST} tail -n 40 /tmp/fine-digital-human.log" >&2
  exit 1
fi
