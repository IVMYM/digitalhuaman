#!/bin/bash
# 一键启动 / 重启完整数字人链路（阿里云 DSW，本机执行）。
# Colab 仍用 scripts/up-xiaoxin.sh。
#
# 和 Colab 版的差别：
#   huggingface.co 从 DSW 连不上，s3fd.pth / wav2lip.pth 改走 hf-mirror。
#   Google Drive 上的预置形象不拉，启动前上传本机 zhengxin 缓存。
#   镜像里经常没有 rsync，同步前用 apt 装上。
#
# 用法:
#   scripts/up-xiaoxin-dsw.sh
#   scripts/up-xiaoxin-dsw.sh check
#   GPU_HOST=colab-livetalking-3.YOUR-HOST.ts.net scripts/up-xiaoxin-dsw.sh
#   FORCE_MATTE=1 scripts/up-xiaoxin-dsw.sh
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPTS_DIR/up-xiaoxin.sh"

sync_repo() {
  local host="$1"
  echo "=== 同步代码到 ${host}（跳过模型、密钥和本地虚拟环境）==="
  ssh "${SSH_OPTS[@]}" "root@${host}" "mkdir -p '$GPU_REPO'"
  if ! ssh "${SSH_OPTS[@]}" "root@${host}" "command -v rsync >/dev/null 2>&1"; then
    echo "=== 远端没有 rsync，正在用 apt 安装 ==="
    ssh "${SSH_OPTS[@]}" "root@${host}" \
      "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null"
  fi
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
    "$ROOT/" "root@${host}:${GPU_REPO}/"
}

run_up() {
  local host
  host="$(resolve_gpu_host)"
  export GPU_HOST="$host"
  echo "=== 一键启动数字人 · DSW · ${host} ==="

  echo "=== 探测 SSH（清掉换机留下的旧主机密钥）==="
  forget_stale_host_key "$host"
  ssh "${SSH_OPTS[@]}" "root@${host}" "hostname; nvidia-smi -L | head -1"

  sync_repo "$host"

  echo "=== 在 DSW 上下载权重（hf-mirror）==="
  ssh "${SSH_OPTS[@]}" "root@${host}" "bash '${GPU_REPO}/scripts/gpu-livetalking-dsw.sh' prepare"

  echo "=== 启动 TURN（规则在 scripts/gpu-turn.sh）==="
  scp "${SSH_OPTS[@]}" "$SCRIPTS/gpu-turn.sh" "root@${host}:${GPU_REPO}/scripts/gpu-turn.sh" >/dev/null
  ssh "${SSH_OPTS[@]}" "root@${host}" "chmod +x '${GPU_REPO}/scripts/gpu-turn.sh' && bash '${GPU_REPO}/scripts/gpu-turn.sh'"

  if [ "${FORCE_MATTE:-0}" != "1" ] && push_local_avatar "$host"; then
    echo "使用本机缓存形象，跳过抠图"
  else
    echo "=== 干净抠图（办公室 → 品红底 → 页面叠 zhengxin.png）==="
    scp "${SSH_OPTS[@]}" "$SCRIPTS/gpu-matte-zhengxin.sh" "root@${host}:${GPU_REPO}/scripts/gpu-matte-zhengxin.sh" >/dev/null
    if [ -s /tmp/dh-matte/silueta.onnx ]; then
      scp "${SSH_OPTS[@]}" /tmp/dh-matte/silueta.onnx "root@${host}:/content/livetalking/silueta.onnx" >/dev/null || true
    elif [ -s "$ROOT/assets/silueta.onnx" ]; then
      scp "${SSH_OPTS[@]}" "$ROOT/assets/silueta.onnx" "root@${host}:/content/livetalking/silueta.onnx" >/dev/null || true
    fi
    ssh "${SSH_OPTS[@]}" "root@${host}" \
      "FORCE_MATTE=${FORCE_MATTE:-0} bash '${GPU_REPO}/scripts/gpu-matte-zhengxin.sh'"
    pull_remote_avatar "$host"
  fi

  echo "=== 带 TURN 启动 LiveTalking（加载抠好的帧）==="
  ssh "${SSH_OPTS[@]}" "root@${host}" "bash '${GPU_REPO}/scripts/gpu-livetalking-dsw.sh' start"

  echo "=== 部署 HTTPS 页面 ==="
  "$SCRIPTS/deploy-fine-digital-human.sh"

  echo "=== 同步 TURN 凭据到本机（本地 start-xiaoxin 可用）==="
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"
  scp "${SSH_OPTS[@]}" "root@${host}:/content/livetalking/turn.env" "$LOCAL_TURN" >/dev/null
  chmod 600 "$LOCAL_TURN"
  if [ -f "$ROOT/.gitignore" ] && ! grep -qxF '.secrets/' "$ROOT/.gitignore"; then
    echo '.secrets/' >>"$ROOT/.gitignore"
  fi
  point_local_env "$host"

  run_check "$host"
}

case "${1:-up}" in
  up|start|restart|"")
    run_up
    ;;
  check)
    run_check "$(resolve_gpu_host)"
    ;;
  *)
    echo "用法: $0 [up|check]" >&2
    echo "  up      完整启动/重启（默认）" >&2
    echo "  check   只检查连通与抠图" >&2
    exit 2
    ;;
esac
