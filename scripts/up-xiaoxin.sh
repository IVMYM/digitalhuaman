#!/bin/bash
# 一键启动 / 重启完整数字人链路（本机执行）。
# 前提：Colab 已跑 colab_google_gpu_bootstrap.py，Tailscale 节点在线。
#
# 流程：
#   1. 发现在线 colab-livetalking*
#   2. 同步 LiveTalking，下载权重，生成 zhengxin
#   3. 启动 TURN（WebRTC 中继，避免约 30 秒断连）
#   4. 干净抠图到品红底（叠 zhengxin.png）
#   5. 带 TURN 重启 LiveTalking
#   6. 部署 HTTPS 页面到 Colab :8000
#   7. 同步 TURN 凭据到本机 .secrets，校正本地 .env
#
# 用法:
#   scripts/up-xiaoxin.sh           # 完整启动/重启
#   scripts/up-xiaoxin.sh check     # 只检查
#   FORCE_MATTE=1 scripts/up-xiaoxin.sh   # 强制重抠并刷新本机缓存
#   GPU_HOST=colab-livetalking-2.YOUR-HOST.ts.net scripts/up-xiaoxin.sh
# 阿里云 DSW 用 scripts/up-xiaoxin-dsw.sh（权重走 hf-mirror，不访问 Google Drive）。
#
# 抠好的形象保存在 assets/avatars/zhengxin/（已 gitignore）。
# GPU 已有品红底则跳过。否则打一个运行时包上传（不含办公室原帧）。
# 若设置 MATTE_ARCHIVE_URL，改为让 GPU 自己下载该压缩包，比本机上传更快。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
GPU_REPO="${GPU_REPO:-/content/livetalking/LiveTalking}"
REMOTE_APP="${REMOTE_APP:-/content/livetalking/fine-digital-human}"
PAGE_PORT="${PAGE_PORT:-8000}"
LT_PORT="${LT_PORT:-8010}"
TURN_PORT="${TURN_PORT:-3478}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)
SECRETS_DIR="$ROOT/.secrets"
LOCAL_TURN="$SECRETS_DIR/turn.env"
# 抠好的形象缓存在工程里，换 Colab 直接上传，不必重抠
LOCAL_AVATAR="${LOCAL_AVATAR:-$ROOT/assets/avatars/zhengxin}"
REMOTE_AVATAR="${GPU_REPO}/data/avatars/zhengxin"

resolve_gpu_host() {
  if [ -n "${GPU_HOST:-}" ]; then
    printf '%s\n' "$GPU_HOST"
    return
  fi
  local name suffix
  # 只选 active/online，跳过带 offline 的行（Colab 换机后旧名常残留）
  name="$(tailscale status | awk '$2 ~ /^colab-livetalking/ && $0 !~ /offline/ { print $2; exit }')"
  if [ -z "$name" ]; then
    echo "没有在线的 colab-livetalking 节点。先在 Colab 跑 colab_google_gpu_bootstrap.py。" >&2
    exit 1
  fi
  suffix="$(tailscale status --json | python3 -c 'import json,sys; name=json.load(sys.stdin)["Self"]["DNSName"].rstrip("."); print(name.split(".",1)[1])')"
  printf '%s.%s\n' "$name" "$suffix"
}

# Colab 是临时机，同名 MagicDNS 常换主机密钥；accept-new 挡不住「已有旧密钥」。
forget_stale_host_key() {
  local host="$1" ip=""
  ssh-keygen -R "$host" >/dev/null 2>&1 || true
  ip="$(tailscale ip -4 "$host" 2>/dev/null || true)"
  if [ -n "$ip" ]; then
    ssh-keygen -R "$ip" >/dev/null 2>&1 || true
  fi
  # 短名也可能写进 known_hosts
  case "$host" in
    *.*) ssh-keygen -R "${host%%.*}" >/dev/null 2>&1 || true ;;
  esac
}

redact_cfg() {
  python3 - <<'PY'
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    print("{}"); raise SystemExit
try:
    d = json.loads(raw)
except Exception:
    print(raw); raise SystemExit
for s in d.get("ice_servers") or []:
    if s.get("credential"):
        s["credential"] = "set"
print(json.dumps(d, ensure_ascii=False))
PY
}

probe() {
  local name="$1" url="$2"
  local code
  code="$(curl -skS -m 10 -o /dev/null -w "%{http_code}" "$url" || echo "000")"
  if [ "$code" = "000" ]; then
    echo "FAIL  $name  $url"
    return 1
  fi
  echo "OK    $name  $url  HTTP $code"
}

point_local_env() {
  local host="$1" envf="$ROOT/fine-digital-human/.env"
  [ -f "$envf" ] || return 0
  python3 - "$envf" "http://${host}:${LT_PORT}" <<'PY'
import pathlib, sys
path, url = pathlib.Path(sys.argv[1]), sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
out, hit = [], False
for row in lines:
    if row.startswith("LIVETALKING_URL="):
        out.append(f"LIVETALKING_URL={url}")
        hit = True
    else:
        out.append(row)
if not hit:
    out.append(f"LIVETALKING_URL={url}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"本机 .env → {url}")
PY
}

local_avatar_ready() {
  [ -f "$LOCAL_AVATAR/coords.pkl" ] && [ -d "$LOCAL_AVATAR/full_imgs" ] && [ -d "$LOCAL_AVATAR/face_imgs" ] || return 1
  python3 - "$LOCAL_AVATAR/full_imgs" <<'PY'
from pathlib import Path
from PIL import Image
import sys
files = sorted(Path(sys.argv[1]).glob("*.png"))
if not files:
    raise SystemExit(1)
c = Image.open(files[0]).convert("RGB").getpixel((0, 0))
raise SystemExit(0 if c == (255, 0, 255) else 1)
PY
}

remote_avatar_ready() {
  local host="$1" expect="$2"
  ssh "${SSH_OPTS[@]}" "root@${host}" \
    "python3 -c \"from pathlib import Path; from PIL import Image; p=Path('${REMOTE_AVATAR}/full_imgs'); f=sorted(p.glob('*.png'));
import sys
sys.exit(0 if f and len(f)==${expect} and Image.open(f[0]).convert('RGB').getpixel((0,0))==(255,0,255) else 1)\""
}

pull_cloud_avatar() {
  local host="$1" url="$2"
  echo "=== GPU 下载抠像包（比本机上传快）==="
  echo "$url"
  ssh "${SSH_OPTS[@]}" "root@${host}" "bash -s" -- "$url" "$REMOTE_AVATAR" <<'EOF'
set -euo pipefail
url="$1"
dest="$2"
mkdir -p "$dest"
tmp="$(mktemp -d)"
wget -q --show-progress -O "$tmp/avatar.tgz" "$url"
tar -xzf "$tmp/avatar.tgz" -C "$dest"
rm -rf "$tmp"
echo "已解压到 $dest"
EOF
}

push_local_avatar() {
  local host="$1" frames
  if ! local_avatar_ready; then
    echo "本机无抠好的形象缓存：$LOCAL_AVATAR"
    return 1
  fi
  frames="$(find "$LOCAL_AVATAR/full_imgs" -name '*.png' | wc -l | tr -d ' ')"
  if remote_avatar_ready "$host" "$frames"; then
    echo "GPU 已有品红底 ${frames} 帧，跳过抠像传输"
    return 0
  fi
  if [ -n "${MATTE_ARCHIVE_URL:-}" ]; then
    pull_cloud_avatar "$host" "$MATTE_ARCHIVE_URL"
    return 0
  fi
  # 运行时只要 full_imgs + face_imgs + coords。办公室原帧约 103MB，不传。
  bytes="$(python3 -c '
import os, sys
root = sys.argv[1]
total = 0
for name in ("coords.pkl", "full_imgs", "face_imgs"):
    path = os.path.join(root, name)
    if os.path.isfile(path):
        total += os.path.getsize(path)
    elif os.path.isdir(path):
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                if filename.startswith("."):
                    continue
                total += os.path.getsize(os.path.join(dirpath, filename))
print(total)
' "$LOCAL_AVATAR")"
  echo "=== 上传运行时抠像（约 $(( (bytes + 1048575) / 1048576 )) MB，不含办公室原帧）==="
  # --disable-copyfile 去掉 macOS 的 provenance，远端就不会逐文件刷警告。
  COPYFILE_DISABLE=1 tar --disable-copyfile --no-xattrs -C "$LOCAL_AVATAR" -cf - coords.pkl full_imgs face_imgs \
    | python3 -u -c '
import sys, time
total = int(sys.argv[1])
sent = 0
last = 0.0
def show(done=False):
    if total <= 0:
        line = f"上传 {sent / 1048576:.1f} MB"
    else:
        pct = 100 if done else min(99, sent * 100 // total)
        line = f"上传 {sent / 1048576:.1f}/{total / 1048576:.1f} MB  {pct}%"
    sys.stderr.write("\r" + line)
    sys.stderr.flush()
while True:
    chunk = sys.stdin.buffer.read(256 * 1024)
    if not chunk:
        break
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    sent += len(chunk)
    now = time.time()
    if now - last >= 0.5:
        last = now
        show()
show(True)
sys.stderr.write("\n")
' "$bytes" \
    | ssh "${SSH_OPTS[@]}" "root@${host}" "mkdir -p '$REMOTE_AVATAR' && tar --warning=no-unknown-keyword -xf - -C '$REMOTE_AVATAR'"
  echo "已上传 ${frames} 帧"
}

pull_remote_avatar() {
  local host="$1"
  echo "=== 拉回抠好的形象到本机工程目录 ==="
  mkdir -p "$LOCAL_AVATAR"
  if ! ssh "${SSH_OPTS[@]}" "root@${host}" "command -v rsync >/dev/null 2>&1"; then
    echo "=== 远端没有 rsync，正在用 apt 安装 ==="
    ssh "${SSH_OPTS[@]}" "root@${host}" "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rsync >/dev/null"
  fi
  rsync -az --delete \
    -e "ssh ${SSH_OPTS[*]}" \
    "root@${host}:${REMOTE_AVATAR}/" "$LOCAL_AVATAR/"
  # 大图不进 git，只留在本机工程目录
  if [ -f "$ROOT/.gitignore" ]; then
    grep -qxF 'assets/avatars/zhengxin/' "$ROOT/.gitignore" || echo 'assets/avatars/zhengxin/' >>"$ROOT/.gitignore"
  fi
  echo "已保存到 $LOCAL_AVATAR （$(ls "$LOCAL_AVATAR/full_imgs" | wc -l | tr -d ' ') 帧）"
}

run_check() {
  local host="$1" failed=0
  echo "=== 检查 ${host} ==="
  ssh "${SSH_OPTS[@]}" "root@${host}" "nvidia-smi -L && tailscale ip -4" || failed=1
  probe "LiveTalking" "http://${host}:${LT_PORT}/" || failed=1
  if nc -z -G 3 "$host" "$TURN_PORT" >/dev/null 2>&1; then
    echo "OK    TURN     ${host}:${TURN_PORT}"
  else
    echo "FAIL  TURN     ${host}:${TURN_PORT}"
    failed=1
  fi
  probe "页面" "https://${host}:${PAGE_PORT}/" || failed=1
  local cfg
  cfg="$(curl -skS -m 8 "https://${host}:${PAGE_PORT}/api/avatar-config" || true)"
  echo "配置  $(printf '%s' "$cfg" | redact_cfg)"
  if ! printf '%s' "$cfg" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ice_transport_policy")=="relay" and d.get("ice_servers") else 1)'; then
    echo "FAIL  页面未下发 TURN relay" >&2
    failed=1
  fi
  if ! ssh "${SSH_OPTS[@]}" "root@${host}" \
    "python3 -c \"from PIL import Image; from pathlib import Path; p=Path('${GPU_REPO}/data/avatars/zhengxin/full_imgs'); f=sorted(p.glob('*.png')); assert f; c=Image.open(f[0]).convert('RGB').getpixel((0,0)); assert c==(255,0,255), c; print('OK    抠图     magenta', len(f), 'frames')\""; then
    echo "FAIL  抠图未完成（角落不是品红）" >&2
    failed=1
  fi
  if [ "$failed" -ne 0 ]; then
    echo "有检查未通过。日志：ssh root@${host} 'tail -n 80 /tmp/livetalking_app.log; tail -n 40 /tmp/fine-digital-human.log'" >&2
    exit 1
  fi
  echo
  echo "页面： https://${host}:${PAGE_PORT}/"
  echo "Chrome 打开，允许麦克风，直接说话；说话会打断当前回答。"
}

run_up() {
  local host
  host="$(resolve_gpu_host)"
  export GPU_HOST="$host"
  echo "=== 一键启动数字人 · ${host} ==="

  echo "=== 探测 SSH（清掉 Colab 换机留下的旧主机密钥）==="
  forget_stale_host_key "$host"
  ssh "${SSH_OPTS[@]}" "root@${host}" "hostname; nvidia-smi -L | head -1"

  echo "=== 同步代码并准备 / 启动 LiveTalking ==="
  "$SCRIPTS/run-and-check.sh" gpu

  echo "=== 启动 TURN ==="
  scp "${SSH_OPTS[@]}" "$SCRIPTS/gpu-turn.sh" "root@${host}:${GPU_REPO}/scripts/gpu-turn.sh" >/dev/null
  ssh "${SSH_OPTS[@]}" "root@${host}" "chmod +x '${GPU_REPO}/scripts/gpu-turn.sh' && bash '${GPU_REPO}/scripts/gpu-turn.sh'"

  # 本机有缓存就上传；否则在 GPU 抠，再拉回工程目录
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

  # TURN 必须在 LiveTalking 进程环境里；抠图后也要重启才能加载新帧
  echo "=== 带 TURN 重启 LiveTalking（加载抠好的帧）==="
  ssh "${SSH_OPTS[@]}" "root@${host}" "bash '${GPU_REPO}/scripts/gpu-livetalking.sh' start"

  echo "=== 部署 HTTPS 页面 ==="
  "$SCRIPTS/deploy-fine-digital-human.sh"

  echo "=== 同步 TURN 凭据到本机（本地 start-xiaoxin 可用）==="
  mkdir -p "$SECRETS_DIR"
  chmod 700 "$SECRETS_DIR"
  scp "${SSH_OPTS[@]}" "root@${host}:/content/livetalking/turn.env" "$LOCAL_TURN" >/dev/null
  chmod 600 "$LOCAL_TURN"
  # 确保 .gitignore 忽略密钥目录
  if [ -f "$ROOT/.gitignore" ] && ! grep -qxF '.secrets/' "$ROOT/.gitignore"; then
    echo '.secrets/' >>"$ROOT/.gitignore"
  fi
  point_local_env "$host"

  run_check "$host"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
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
fi
