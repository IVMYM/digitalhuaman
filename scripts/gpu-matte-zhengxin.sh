#!/bin/bash
# 在 Colab GPU 上把 zhengxin 全身帧抠成品红底。
# 办公室原帧备份到 full_imgs_office；FORCE_MATTE=1 强制重抠。
# 用法（GPU 上）: scripts/gpu-matte-zhengxin.sh
set -euo pipefail

REPO="${LIVETALKING_REPO:-/content/livetalking/LiveTalking}"
AVATAR_ID="${CUSTOM_AVATAR_ID:-zhengxin}"
MODEL="${MATTE_MODEL:-/content/livetalking/silueta.onnx}"
MODEL_URL="${MATTE_MODEL_URL:-https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx}"
STORE="${LIVETALKING_STORE:-/mnt/workspace/livetalking/models}"
FORCE="${FORCE_MATTE:-0}"

cd "$REPO"
src="data/avatars/${AVATAR_ID}/full_imgs"
backup="data/avatars/${AVATAR_ID}/full_imgs_office"

if [ ! -d "$src" ]; then
  echo "没有形象帧：$src" >&2
  exit 1
fi

need=0
if [ "$FORCE" = "1" ]; then
  need=1
else
  corner="$(python3 - "$src" <<'PY'
from pathlib import Path
from PIL import Image
p = Path(__import__("sys").argv[1])
files = sorted(p.glob("*.png"))
if not files:
    print("empty"); raise SystemExit
c = Image.open(files[0]).convert("RGB").getpixel((0, 0))
print("%d,%d,%d" % c)
PY
)"
  case "$corner" in
    255,0,255) echo "已是品红底，跳过抠图（FORCE_MATTE=1 可重做）" ;;
    *) need=1 ;;
  esac
fi

if [ "$need" != "1" ]; then
  exit 0
fi

if [ ! -s "$MODEL" ] && [ -s "$STORE/silueta.onnx" ]; then
  echo "从 $STORE 恢复 silueta.onnx"
  mkdir -p "$(dirname "$MODEL")"
  cp -a "$STORE/silueta.onnx" "$MODEL"
fi
WHEELHOUSE="${LIVETALKING_WHEELHOUSE:-/mnt/workspace/livetalking/wheels/pip}"
install_onnxruntime() {
  if compgen -G "$WHEELHOUSE/*.whl" >/dev/null 2>&1 \
    && python3 -m pip install -q --no-index --find-links "$WHEELHOUSE" onnxruntime; then
    return 0
  fi
  python3 -m pip install -q onnxruntime
}
if [ ! -s "$MODEL" ]; then
  echo "下载抠图模型 $(basename "$MODEL")"
  install_onnxruntime
  wget -q --show-progress -O "${MODEL}.partial" "$MODEL_URL"
  mv "${MODEL}.partial" "$MODEL"
fi
if [ -s "$MODEL" ] && [ -d "$(dirname "$STORE")" ]; then
  mkdir -p "$STORE"
  if [ ! -s "$STORE/silueta.onnx" ] || [ "$(stat -c%s "$MODEL")" != "$(stat -c%s "$STORE/silueta.onnx")" ]; then
    echo "备份 silueta.onnx -> $STORE"
    cp -a "$MODEL" "$STORE/silueta.onnx.partial"
    mv "$STORE/silueta.onnx.partial" "$STORE/silueta.onnx"
  fi
fi
install_onnxruntime >/dev/null

python3 - "$src" "$backup" "$MODEL" <<'PY'
import shutil
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import cv2
import onnxruntime as ort

src, backup, model = map(Path, sys.argv[1:4])
if not backup.exists():
    shutil.copytree(src, backup)
    print("backed up", len(list(backup.glob("*.png"))))
else:
    for f in sorted(backup.glob("*.png")):
        shutil.copy2(f, src / f.name)
    print("restored", len(list(backup.glob("*.png"))))

sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
iname = sess.get_inputs()[0].name
mean = np.array([0.485, 0.456, 0.406], np.float32)
std = np.array([0.229, 0.224, 0.225], np.float32)
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
erode_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
files = sorted(src.glob("*.png"))
for i, f in enumerate(files):
    src_img = backup / f.name if (backup / f.name).exists() else f
    img = Image.open(src_img).convert("RGB")
    small = img.resize((320, 320), Image.Resampling.LANCZOS)
    arr = np.asarray(small).astype(np.float32)
    arr = arr / max(float(arr.max()), 1e-6)
    arr = ((arr - mean) / std).transpose(2, 0, 1)[None]
    pred = np.squeeze(sess.run(None, {iname: arr})[0])
    pred = (pred - pred.min()) / (pred.max() - pred.min() + 1e-8)
    mask = np.asarray(
        Image.fromarray((pred * 255).astype(np.uint8)).resize(img.size, Image.Resampling.LANCZOS)
    )
    person = (mask >= 128).astype(np.uint8) * 255
    person = cv2.morphologyEx(person, cv2.MORPH_CLOSE, kernel, iterations=2)
    person = cv2.morphologyEx(person, cv2.MORPH_OPEN, erode_k, iterations=1)
    person = cv2.erode(person, erode_k, iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats((person > 0).astype(np.uint8), 8)
    if n > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = 1 + int(np.argmax(areas))
        person = np.where(labels == keep, 255, 0).astype(np.uint8)
    rgb = np.asarray(img).copy()
    bg = person < 128
    rgb[bg] = (255, 0, 255)
    Image.fromarray(rgb).save(f)
    if i % 25 == 0 or i == len(files) - 1:
        print(i, f.name, "bg", round(float(bg.mean()), 3), "corner", tuple(int(x) for x in rgb[0, 0]))
print("done", len(files))
PY
