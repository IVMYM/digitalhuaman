#!/bin/bash
# 在阿里云 DSW 上执行。权重从 hf-mirror 下载，不访问 huggingface.co，也不拉 Google Drive。
# 预置形象 wav2lip256_avatar1 只在网盘里；本机一键脚本会在启动前上传 zhengxin。
# start 会先跑同目录的 gpu-turn.sh：放行 Tailscale 的 100.64.0.0/10，不设带宽配额。
# 用法: gpu-livetalking-dsw.sh [prepare|start|all]
set -euo pipefail

REPO="${LIVETALKING_REPO:-/content/livetalking/LiveTalking}"
CACHE="${LIVETALKING_CACHE:-/content/livetalking/model_cache}"
# DSW 系统盘会清掉。权重和 cu128 wheel 放 NAS，下次启动先从这里恢复。
STORE="${LIVETALKING_STORE:-/mnt/workspace/livetalking/models}"
TORCH_ARCHIVE="${LIVETALKING_TORCH_ARCHIVE:-/mnt/workspace/livetalking/wheels/torch-cu128.tar.gz}"
WHEELHOUSE="${LIVETALKING_WHEELHOUSE:-/mnt/workspace/livetalking/wheels/pip}"
STOCK_ID="${STOCK_AVATAR_ID:-wav2lip256_avatar1}"
AVATAR_ID="$STOCK_ID"
LOG="${LIVETALKING_LOG:-/tmp/livetalking_app.log}"
PID_FILE="${LIVETALKING_PID:-/tmp/livetalking_app.pid}"
CUSTOM_ID="${CUSTOM_AVATAR_ID:-zhengxin}"
AVATAR_STORE="${LIVETALKING_AVATAR_STORE:-/mnt/workspace/livetalking/avatars/${CUSTOM_ID}}"
CUSTOM_VIDEO="${CUSTOM_AVATAR_VIDEO:-assets/avatar_idle.mp4}"
HF_MIRROR="${HF_MIRROR:-https://hf-mirror.com}"
S3FD_URL="${S3FD_URL:-${HF_MIRROR}/mide7x/wav2lip-models/resolve/main/s3fd.pth}"
WAV2LIP_URL="${WAV2LIP_URL:-${HF_MIRROR}/shibing624/ai-avatar-wav2lip/resolve/main/wav2lip.pth}"

cd "$REPO"
mkdir -p "$CACHE" models data/avatars avatars/wav2lip/face_detection/detection/sfd
export HF_ENDPOINT="$HF_MIRROR"
export PIP_ROOT_USER_ACTION=ignore

download() {
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then
    echo "已存在 $(basename "$dest")"
    return 0
  fi
  echo "下载 $(basename "$dest")"
  echo "$url"
  rm -f "$dest.partial"
  if ! wget --timeout=30 --tries=3 --show-progress -O "$dest.partial" "$url"; then
    rm -f "$dest.partial"
    echo "下载失败: $url" >&2
    return 1
  fi
  if [ ! -s "$dest.partial" ]; then
    rm -f "$dest.partial"
    echo "下载结果为空: $url" >&2
    return 1
  fi
  mv "$dest.partial" "$dest"
}

# 本地没有时从 NAS 恢复。恢复成功返回 0。
restore_model() {
  local name="$1" dest="$2"
  if [ -s "$dest" ]; then
    return 0
  fi
  if [ -s "$STORE/$name" ]; then
    echo "从 $STORE 恢复 $name"
    mkdir -p "$(dirname "$dest")"
    cp -a "$STORE/$name" "$dest"
    return 0
  fi
  return 1
}

# 本地有、NAS 没有或大小不一致时写回 NAS。
backup_model() {
  local name="$1" src="$2"
  if [ ! -s "$src" ]; then
    return 0
  fi
  if [ ! -d "$(dirname "$STORE")" ]; then
    echo "NAS 不在，跳过备份 $name" >&2
    return 0
  fi
  mkdir -p "$STORE"
  if [ -s "$STORE/$name" ] && [ "$(stat -c%s "$src")" = "$(stat -c%s "$STORE/$name")" ]; then
    echo "NAS 已有 $name"
    return 0
  fi
  echo "备份 $name -> $STORE"
  cp -a "$src" "$STORE/$name.partial"
  mv "$STORE/$name.partial" "$STORE/$name"
}

# 镜像重置后这些包不在系统里。有本地 wheel 就不再访问 PyPI。
install_python_deps() {
  if compgen -G "$WHEELHOUSE/*.whl" >/dev/null 2>&1; then
    echo "从 $WHEELHOUSE 安装 Python 依赖"
    if python3 -m pip install -q --upgrade-strategy only-if-needed --no-index --find-links "$WHEELHOUSE" "$@"; then
      return 0
    fi
    echo "本地 wheel 不全，改从网络补齐" >&2
  fi
  python3 -m pip install -q --upgrade-strategy only-if-needed "$@"
}

restore_avatar() {
  local dest="data/avatars/${CUSTOM_ID}"
  if [ -f "$dest/coords.pkl" ] && [ -d "$dest/full_imgs" ]; then
    return 0
  fi
  if [ -f "$AVATAR_STORE/coords.pkl" ] && [ -d "$AVATAR_STORE/full_imgs" ]; then
    echo "从 NAS 恢复形象 ${CUSTOM_ID}"
    mkdir -p "$dest"
    cp -a "$AVATAR_STORE/." "$dest/"
  fi
}

backup_avatar() {
  local src="data/avatars/${CUSTOM_ID}" src_n store_n
  [ -f "$src/coords.pkl" ] && [ -d "$src/full_imgs" ] || return 0
  [ -d /mnt/workspace ] || return 0
  src_n="$(find "$src/full_imgs" -name '*.png' | wc -l)"
  store_n=0
  if [ -d "$AVATAR_STORE/full_imgs" ]; then
    store_n="$(find "$AVATAR_STORE/full_imgs" -name '*.png' | wc -l)"
  fi
  if [ "$src_n" != "0" ] && [ "$src_n" = "$store_n" ] && [ -f "$AVATAR_STORE/coords.pkl" ]; then
    echo "NAS 已有形象 ${CUSTOM_ID}（${src_n} 帧）"
    return 0
  fi
  echo "备份形象 ${CUSTOM_ID}（${src_n} 帧）-> $AVATAR_STORE"
  mkdir -p "$AVATAR_STORE"
  cp -a "$src/." "$AVATAR_STORE/"
}

# OCI 上下好的 cu128 wheel。先只装 torch 本体; 若镜像没有 NVIDIA 运行库 (libcudart.so.12 等),
# import torch 会失败, 届时补装 nvidia-*-cu12 依赖 (见 ensure_torch_cu128 末尾)。
ensure_torch_cu128() {
  local ver src="${TORCH_WHEEL_SRC:-/tmp/torch-cu128.tar.gz}"
  ver="$(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null || true)"
  if [ -s "$src" ] && [ -d /mnt/workspace ]; then
    mkdir -p "$(dirname "$TORCH_ARCHIVE")"
    if [ ! -s "$TORCH_ARCHIVE" ] || [ "$(stat -c%s "$src")" != "$(stat -c%s "$TORCH_ARCHIVE")" ]; then
      echo "备份 torch cu128 wheel -> $TORCH_ARCHIVE"
      cp -a "$src" "$TORCH_ARCHIVE.partial"
      mv "$TORCH_ARCHIVE.partial" "$TORCH_ARCHIVE"
    else
      echo "NAS 已有 torch cu128 wheel"
    fi
  fi
  case "$ver" in
    *cu128*)
      echo "torch 已是 $ver"
      return 0
      ;;
  esac
  if [ ! -s "$TORCH_ARCHIVE" ]; then
    echo "没有 cu128 wheel，继续使用当前 torch: ${ver:-未安装}" >&2
    return 0
  fi
  echo "从 NAS 安装 torch cu128（当前: ${ver:-未安装}）"
  local tmp
  tmp="$(mktemp -d)"
  tar -xzf "$TORCH_ARCHIVE" -C "$tmp"
  python3 -m pip install -q --force-reinstall --no-deps "$tmp"/torch-cu128/*.whl
  rm -rf "$tmp"
  if python3 -c 'import torch' >/dev/null 2>&1; then
    echo "torch import OK: $(python3 -c 'import torch; print(torch.__version__)' 2>/dev/null)"
    return 0
  fi
  echo "torch 本体已装但 import 失败（缺 CUDA 12 运行库），安装 NAS 上全部 cu12 wheel" >&2
  install_cuda_runtime_wheels
  setup_cuda_runtime
  python3 -c 'import torch; print("torch OK", torch.__version__, "cuda:", torch.cuda.is_available())'
}

# 镜像自带 torchaudio 是 cu13 构建, 与 cu128 torch 混用会让 SenseVoice ASR 推理报错
# (PyTorch/TorchAudio CUDA 版本不一致)。wheelhouse 有同版 cu128 wheel, 对齐它。
ensure_torchaudio_cu128() {
  local taver wheel
  taver="$(python3 -c 'import torchaudio; print(torchaudio.__version__)' 2>/dev/null || true)"
  case "$taver" in
    *cu128*) echo "torchaudio 已是 $taver"; return 0 ;;
  esac
  wheel="$(compgen -G "$WHEELHOUSE/torchaudio-*cu128*.whl" | head -1 || true)"
  if [ -z "$wheel" ]; then
    echo "wheelhouse 缺 torchaudio cu128 wheel，ASR 可能不可用（当前: ${taver:-未安装}）" >&2
    return 0
  fi
  echo "对齐 torchaudio -> cu128（当前: ${taver:-未安装}）"
  python3 -m pip install -q --no-index --no-deps --force-reinstall "$wheel"
  python3 -c 'import torchaudio; print("torchaudio OK", torchaudio.__version__)'
}

CUDA_RUNTIME_PKGS=(
  nvidia-cuda-runtime-cu12 nvidia-cuda-nvrtc-cu12 nvidia-cuda-cupti-cu12
  nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12
  nvidia-curand-cu12 nvidia-cusolver-cu12 nvidia-cusparse-cu12
  nvidia-nccl-cu12 nvidia-nvjitlink-cu12
)

setup_cuda_runtime() {
  local site d paths=""
  site="$(python3 -c 'import site; print(site.getsitepackages()[0])')"
  for d in "$site"/nvidia/*/lib; do
    [ -d "$d" ] || continue
    paths="${paths:+$paths:}$d"
  done
  if [ -n "$paths" ]; then
    export LD_LIBRARY_PATH="${paths}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fi
}

install_cuda_runtime_wheels() {
  local wheels=()
  while IFS= read -r item; do
    wheels+=("$item")
  done < <(compgen -G "$WHEELHOUSE/nvidia_*_cu12*.whl" || true)
  if [ "${#wheels[@]}" -eq 0 ]; then
    echo "NAS wheelhouse 缺少 nvidia_*_cu12 wheel" >&2
    return 1
  fi
  # 不让 pip 把 DSW 现有 CUDA 13 包重新解析进来；这些 wheel 自带所需 .so。
  python3 -m pip install -q --no-index --no-deps --force-reinstall "${wheels[@]}"
}

ensure_cuda_runtime() {
  setup_cuda_runtime
  if python3 -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then
    return 0
  fi
  echo "补装 NVIDIA CUDA 12 运行库（libcudart/libcublas 等）"
  install_cuda_runtime_wheels
  setup_cuda_runtime
  python3 -c 'import torch; print("CUDA:", torch.version.cuda, "available:", torch.cuda.is_available())'
}

prepare() {
  echo "=== GPU 依赖 ==="
  ensure_torch_cu128
  ensure_torchaudio_cu128
  ensure_cuda_runtime
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ffmpeg psmisc >/dev/null
  # 镜像里已有 numpy / torch（vLLM、ModelScope）。缺了再装，已有的不升级。
  local pkgs=(
    aiohttp aiohttp_cors aiortc edge-tts opencv-python-headless
    librosa soundfile resampy einops flask openai pyyaml python-dotenv
  )
  python3 -c 'import numpy' >/dev/null 2>&1 || pkgs+=(numpy)
  python3 -c 'import scipy' >/dev/null 2>&1 || pkgs+=(scipy)
  install_python_deps "${pkgs[@]}"

  local s3fd="avatars/wav2lip/face_detection/detection/sfd/s3fd.pth"
  local wav2lip="models/wav2lip.pth"
  echo "=== 人脸检测权重（NAS 优先，没有再下 hf-mirror）==="
  restore_model s3fd.pth "$s3fd" || download "$S3FD_URL" "$s3fd"
  backup_model s3fd.pth "$s3fd"

  echo "=== Wav2Lip 权重（NAS 优先，没有再下 hf-mirror）==="
  restore_model wav2lip.pth "$wav2lip" || download "$WAV2LIP_URL" "$wav2lip"
  backup_model wav2lip.pth "$wav2lip"

  if [ -n "${WAV2LIP_AVATAR_URL:-}" ] && [ ! -f "data/avatars/${STOCK_ID}/coords.pkl" ]; then
    echo "=== 下载预置形象 ==="
    download "$WAV2LIP_AVATAR_URL" "$CACHE/${STOCK_ID}.tgz"
    rm -rf "data/avatars/${STOCK_ID}"
    mkdir -p "data/avatars/${STOCK_ID}"
    tar -xzf "$CACHE/${STOCK_ID}.tgz" -C "data/avatars/${STOCK_ID}" --strip-components=0
  fi

  restore_avatar
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
    backup_avatar
    AVATAR_ID="$CUSTOM_ID"
  elif [ ! -f "data/avatars/${STOCK_ID}/coords.pkl" ]; then
    echo "权重已就绪。DSW 不拉 Google Drive 预置形象，等本机上传 ${CUSTOM_ID} 后再启动。"
    return 0
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
  ensure_cuda_runtime
  if [ -d "data/avatars/${CUSTOM_ID}/full_imgs" ] && [ -f "data/avatars/${CUSTOM_ID}/coords.pkl" ]; then
    AVATAR_ID="$CUSTOM_ID"
  fi
  if [ ! -f "data/avatars/${AVATAR_ID}/coords.pkl" ]; then
    echo "没有可用形象 data/avatars/${AVATAR_ID}。先上传 ${CUSTOM_ID}，或设置 WAV2LIP_AVATAR_URL。" >&2
    return 1
  fi
  turn_sh="$(cd "$(dirname "$0")" && pwd)/gpu-turn.sh"
  if [ ! -f "$turn_sh" ]; then
    echo "缺少 $turn_sh，无法启动 TURN" >&2
    return 1
  fi
  echo "=== 启动 TURN ==="
  bash "$turn_sh"
  echo "=== 启动 LiveTalking :8010 形象 ${AVATAR_ID} ==="
  stop_app
  turn_env="${TURN_ENV_FILE:-/content/livetalking/turn.env}"
  if [ ! -f "$turn_env" ]; then
    echo "缺少 $turn_env" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  . "$turn_env"
  set +a
  export TURN_URL="turn:127.0.0.1:${TURN_PORT:-3478}?transport=tcp"
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
    echo "用法: $0 [prepare|start|all]" >&2
    exit 2
    ;;
esac
