#!/bin/bash
# 在 Colab GPU 上执行。权重只在这台机器下载，不从本机拷贝。
# 用法: gpu-livetalking.sh [all|prepare|start]
set -euo pipefail

REPO="${LIVETALKING_REPO:-/content/livetalking/LiveTalking}"
CACHE="${LIVETALKING_CACHE:-/content/livetalking/model_cache}"
STOCK_ID="${STOCK_AVATAR_ID:-wav2lip256_avatar1}"
AVATAR_ID="$STOCK_ID"
LOG="${LIVETALKING_LOG:-/tmp/livetalking_app.log}"
PID_FILE="${LIVETALKING_PID:-/tmp/livetalking_app.pid}"
GDRIVE_FOLDER="${GDRIVE_FOLDER:-1FOC_MD6wdogyyX_7V1d4NDIO7P9NlSAJ}"
CUSTOM_ID="${CUSTOM_AVATAR_ID:-zhengxin}"
CUSTOM_VIDEO="${CUSTOM_AVATAR_VIDEO:-assets/avatar_idle.mp4}"

cd "$REPO"
mkdir -p "$CACHE" models data/avatars avatars/wav2lip/face_detection/detection/sfd

download() {
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then
    echo "已存在 $(basename "$dest")"
    return 0
  fi
  echo "下载 $(basename "$dest")"
  wget -q --show-progress -O "$dest.partial" "$url"
  mv "$dest.partial" "$dest"
}

prepare() {
  echo "=== GPU 依赖 ==="
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ffmpeg psmisc >/dev/null
  python3 -m pip install -q --upgrade pip
  python3 -m pip install -q \
    aiohttp aiohttp_cors aiortc edge-tts opencv-python-headless \
    librosa soundfile resampy einops flask openai pyyaml python-dotenv \
    numpy scipy gdown huggingface_hub

  echo "=== 在 GPU 上下载人脸检测权重 ==="
  download \
    "https://huggingface.co/mide7x/wav2lip-models/resolve/main/s3fd.pth" \
    "avatars/wav2lip/face_detection/detection/sfd/s3fd.pth"

  echo "=== 在 GPU 上下载 Wav2Lip 与预置形象 ==="
  if [ ! -s models/wav2lip.pth ] || [ ! -d "data/avatars/${STOCK_ID}/full_imgs" ]; then
    python3 -m gdown --folder "$GDRIVE_FOLDER" -O "$CACHE/gdrive_wav2lip" --remaining-ok
  fi

  if [ ! -s models/wav2lip.pth ]; then
    local weight
    weight="$(find "$CACHE/gdrive_wav2lip" -type f \( -name 'wav2lip256.pth' -o -name 'wav2lip.pth' \) | head -1)"
    if [ -z "$weight" ]; then
      download \
        "https://huggingface.co/shibing624/ai-avatar-wav2lip/resolve/main/wav2lip.pth" \
        "models/wav2lip.pth"
    else
      cp "$weight" models/wav2lip.pth
    fi
  fi

  local avatar_dir="data/avatars/${STOCK_ID}"
  extract_stock() {
    local archive
    archive="$(find "$CACHE/gdrive_wav2lip" -type f -name "${STOCK_ID}.tar.gz" | head -1)"
    if [ -z "$archive" ]; then
      echo "没有找到 ${STOCK_ID}.tar.gz" >&2
      return 1
    fi
    rm -rf "$avatar_dir"
    tar -xzf "$archive" -C data/avatars
    local nested="${avatar_dir}/${STOCK_ID}"
    if [ -d "$nested" ]; then
      local tmp
      tmp="$(mktemp -d)"
      mv "$nested" "$tmp/avatar"
      rm -rf "$avatar_dir"
      mv "$tmp/avatar" "$avatar_dir"
      rm -rf "$tmp"
    fi
  }
  if [ ! -d "${avatar_dir}/full_imgs" ] || [ ! -f "${avatar_dir}/coords.pkl" ]; then
    extract_stock || true
  fi
  if [ ! -f "${avatar_dir}/coords.pkl" ]; then
    echo "形象目录缺少 coords.pkl，重解压一次: $avatar_dir" >&2
    extract_stock || true
  fi
  if [ ! -f "${avatar_dir}/coords.pkl" ]; then
    echo "形象目录缺少 coords.pkl: $avatar_dir" >&2
    exit 1
  fi

  if [ ! -d "data/avatars/${CUSTOM_ID}/full_imgs" ] && [ -s "$CUSTOM_VIDEO" ]; then
    echo "=== 从 ${CUSTOM_VIDEO} 生成默认形象 ${CUSTOM_ID} ==="
    python3 -m avatars.wav2lip.genavatar \
      --video_path "$CUSTOM_VIDEO" \
      --avatar_id "$CUSTOM_ID" \
      --img_size 256 \
      --face_det_batch_size 2 \
      --pads 0 10 0 0
  fi
  if [ -d "data/avatars/${CUSTOM_ID}/full_imgs" ] && [ -f "data/avatars/${CUSTOM_ID}/coords.pkl" ]; then
    AVATAR_ID="$CUSTOM_ID"
  fi

  ln -sfn "$AVATAR_ID" data/avatars/test01
  echo "默认形象 ${AVATAR_ID}"
}

stop_app() {
  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 8010/tcp >/dev/null 2>&1 || true
  fi
  sleep 1
}

start_app() {
  if [ -d "data/avatars/${CUSTOM_ID}/full_imgs" ] && [ -f "data/avatars/${CUSTOM_ID}/coords.pkl" ]; then
    AVATAR_ID="$CUSTOM_ID"
  fi
  echo "=== 启动 LiveTalking :8010 形象 ${AVATAR_ID} ==="
  stop_app
  turn_env="${TURN_ENV_FILE:-/content/livetalking/turn.env}"
  if [ -f "$turn_env" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$turn_env"
    set +a
    export TURN_URL="turn:127.0.0.1:${TURN_PORT:-3478}?transport=tcp"
  fi
  nohup python3 app.py \
    --transport webrtc \
    --model wav2lip \
    --avatar_id "$AVATAR_ID" \
    --tts edgetts \
    --REF_FILE zh-CN-YunxiaNeural \
    --batch_size 4 \
    --listenport 8010 \
    >"$LOG" 2>&1 &
  echo $! >"$PID_FILE"

  for _ in $(seq 1 90); do
    if python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8010/", timeout=2)' >/dev/null 2>&1; then
      echo "LiveTalking 已监听 8010，日志 $LOG"
      return 0
    fi
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "进程已退出，日志末尾：" >&2
      tail -n 80 "$LOG" >&2 || true
      return 1
    fi
    sleep 2
  done
  echo "端口未就绪，日志末尾：" >&2
  tail -n 80 "$LOG" >&2 || true
  return 1
}

case "${1:-all}" in
  prepare) prepare ;;
  start) start_app ;;
  all) prepare; start_app ;;
  *)
    echo "用法: $0 [all|prepare|start]" >&2
    exit 2
    ;;
esac
