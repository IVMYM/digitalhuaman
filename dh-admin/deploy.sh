#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 docker。请先安装 Docker Engine 和 Compose 插件。"
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已生成 .env。请先修改 JWT_SECRET、ENCRYPTION_KEY、ADMIN_PASSWORD、RUNTIME_API_TOKEN，再重新执行 ./deploy.sh"
  exit 1
fi

if grep -q "please-change-me" .env; then
  echo ".env 里还有 please-change-me 占位符。请换成随机密钥和管理员密码后再启动。"
  exit 1
fi

avail_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if [[ "${avail_kb}" -lt 900000 ]]; then
  echo "提示：当前 MemAvailable 约 $((avail_kb / 1024)) MB。构建前端时 Node 可能吃紧。"
  echo "若构建失败，先停掉不必要的容器，或在另一台机器构建后 docker save / docker load。"
fi

mkdir -p data
docker compose up -d --build

port="$(grep -E '^APP_PORT=' .env | tail -n1 | cut -d= -f2- | tr -d ' \"' || true)"
port="${port:-18200}"
echo "已启动。本机访问 http://127.0.0.1:${port}"
echo "端口只绑定 127.0.0.1。对 GPU 服务器开放时，用 nginx 或隧道，不要改成 0.0.0.0，除非你清楚风险。"
