#!/bin/bash
# 在 Colab 或魔搭 DSW 上启动只给本机数字人用的 TURN。
# 两边都是用户态 Tailscale：浏览器经 TCP 连进来，媒体不再走约 30 秒被掐掉的直连 UDP。
set -euo pipefail

ENV_FILE="${TURN_ENV_FILE:-/content/livetalking/turn.env}"
CONF="${TURN_CONF:-/content/livetalking/turnserver.conf}"
PID_FILE="${TURN_PID:-/tmp/turnserver.pid}"
PORT="${TURN_PORT:-3478}"

mkdir -p "$(dirname "$ENV_FILE")"
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  pass="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  host="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  cat >"$ENV_FILE" <<EOF
TURN_USER=livetalking
TURN_PASS=${pass}
TURN_PORT=${PORT}
TURN_PUBLIC_HOST=${host}
EOF
else
  host="$(python3 - "$ENV_FILE" <<'PY'
import pathlib, sys
vals = {}
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip()
dns = __import__("json").load(__import__("sys").stdin) if False else ""
print(vals.get("TURN_PUBLIC_HOST", ""))
PY
)"
  # 节点名会变，每次按当前 MagicDNS 改公开地址，密码保持不变。
  dns="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  python3 - "$ENV_FILE" "$dns" <<'PY'
import pathlib, sys
path, dns = pathlib.Path(sys.argv[1]), sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
out, seen = [], False
for line in lines:
    if line.startswith("TURN_PUBLIC_HOST="):
        out.append(f"TURN_PUBLIC_HOST={dns}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"TURN_PUBLIC_HOST={dns}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

relay_ip="$(ip -4 route get 1.1.1.1 | python3 -c 'import sys; p=sys.stdin.read().split(); print(p[p.index("src")+1])')"
# 浏览器只能访问 Tailscale 地址。不写 external-ip 时，coturn 会把中继地址报成 172.x，视频出不去。
public_ip="$(tailscale ip -4 | head -1)"
if [ -z "$public_ip" ]; then
  echo "没有 Tailscale IPv4，浏览器收不到中继地址" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
if ! command -v turnserver >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq coturn >/dev/null
fi

cat >"$CONF" <<EOF
listening-port=${TURN_PORT}
listening-ip=0.0.0.0
relay-ip=${relay_ip}
external-ip=${public_ip}/${relay_ip}
fingerprint
lt-cred-mech
user=${TURN_USER}:${TURN_PASS}
realm=livetalking
no-cli
no-tls
no-dtls
no-multicast-peers
allow-loopback-peers
# coturn 默认拒绝 100.64.0.0/10。中继地址是 Tailscale IP，不放行的话两端无法互转。
allowed-peer-ip=100.64.0.0-100.127.255.255
allowed-peer-ip=${relay_ip}
allowed-peer-ip=${public_ip}
log-file=/tmp/turnserver.log
simple-log
EOF
chmod 600 "$CONF" "$ENV_FILE"

if [ -f "$PID_FILE" ]; then
  old="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    kill "$old" 2>/dev/null || true
    sleep 0.4
  fi
fi
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${TURN_PORT}/tcp" >/dev/null 2>&1 || true
fi
nohup turnserver -c "$CONF" --pidfile "$PID_FILE" >/tmp/turnserver.nohup 2>&1 &
echo $! >"$PID_FILE"

for _ in $(seq 1 20); do
  if python3 -c "import socket; s=socket.create_connection(('127.0.0.1', ${TURN_PORT}), 2); s.close()" >/dev/null 2>&1; then
    echo "TURN 已监听 ${TURN_PORT}，对浏览器公布 ${public_ip}，本机中继 ${relay_ip}"
    exit 0
  fi
  sleep 0.3
done
echo "TURN 没有监听，日志末尾：" >&2
tail -n 40 /tmp/turnserver.log /tmp/turnserver.nohup >&2 || true
exit 1
