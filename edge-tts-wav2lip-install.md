# LiveTalking 免费套：Edge-TTS + Wav2Lip

按官方文档整理，适合自装验证。Edge-TTS 默认内置，无需另起 TTS 服务；需能访问微软 Edge 语音接口。

参考：
- 安装：[GitHub README](https://github.com/lipku/LiveTalking)
- 用法：[Usage](https://doc.livetalking.ai/en/docs/usage/)

## 0. 环境要求

- Linux 推荐（Ubuntu 22.04 已验证）；Windows 需自行处理 CUDA / ffmpeg
- NVIDIA GPU + 驱动；`nvidia-smi` 能看出版本
- 能访问外网（Edge-TTS）
- 端口：TCP **8010**；WebRTC 需放行 UDP（文档写 1–65536，内网可先试）

## 1. 拉代码与 Python 环境

官方当前推荐：**Python 3.12 + PyTorch 2.9.1 + CUDA 12.8**。

```bash
git clone https://github.com/lipku/LiveTalking.git
cd LiveTalking

conda create -n livetalking python=3.12 -y
conda activate livetalking

# CUDA 不是 12.8 时，到 https://pytorch.org/get-started/previous-versions 换对应 wheel
pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 \
  --index-url https://download.pytorch.org/whl/cu128

pip install -r requirements.txt
# requirements 已含 edge_tts；缺 ffmpeg 时自行安装：
# Ubuntu: sudo apt install -y ffmpeg
# conda: conda install -c conda-forge ffmpeg
```

装完自检：

```bash
python -c "import torch, edge_tts; print(torch.__version__, torch.cuda.is_available())"
edge-tts --list-voices | head
```

## 2. 下载 Wav2Lip 模型与默认形象

夸克网盘（官方）：https://pan.quark.cn/s/83a750323ef0

放到工程里：

| 文件 | 放到 |
|------|------|
| `s3fd.pth` | `wav2lip/face_detection/detection/sfd/s3fd.pth` |
| `wav2lip256.pth` | `models/wav2lip.pth`（改名） |
| `wav2lip256_avatar1.tar.gz` 解压后的目录 | `data/avatars/wav2lip256_avatar1/` |

目录示意：

```text
LiveTalking/
  models/wav2lip.pth
  wav2lip/face_detection/detection/sfd/s3fd.pth
  data/avatars/wav2lip256_avatar1/
```

## 3. 启动（Edge-TTS 默认）

```bash
conda activate livetalking
cd /path/to/LiveTalking

# 默认 --tts edgetts，可显式写出
python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id wav2lip256_avatar1 \
  --tts edgetts \
  --REF_FILE zh-CN-YunxiaNeural
```

浏览器打开：`http://本机IP:8010`

换音色：把 `--REF_FILE` 换成 Edge 语音名，例如：

- 中文女：`zh-CN-XiaoxiaoNeural`、`zh-CN-YunxiaNeural`
- 中文男：`zh-CN-YunxiNeural`、`zh-CN-YunjianNeural`
- 英文：`en-US-AriaNeural`

查全部音色：`edge-tts --list-voices`

可选：`--batch_size 8`（显存紧就调小）提高吞吐。

## 4. 自建形象（可选）

素材必须是**闭嘴、无声**视频：

```bash
python -m avatars.wav2lip.genavatar \
  --video_path /path/to/silent.mp4 \
  --img_size 256 \
  --avatar_id my_avatar

# 卡顿可加：--face_det_batch_size 2
# 输出在 data/avatars/my_avatar
```

启动时改 `--avatar_id my_avatar`。

## 5. 连通性自测

1. 页面能打开，点连接后有画面  
2. 输入一句话，应先听到 Edge 语音，嘴型再跟  
3. 若只有画面无声音：检查本机是否访问 Edge 被墙/代理；试 `edge-tts --text "你好" --voice zh-CN-YunxiaNeural --write-media /tmp/t.mp3`  
4. WebRTC 连不上：HTTPS/本机 localhost 更稳；跨机需公网 IP + UDP；可把站点加入浏览器「不安全来源视为安全」白名单（仅调试）

## 6. 常见问题

| 现象 | 处理 |
|------|------|
| CUDA / torch 对不上 | 按本机 `nvidia-smi` 的 CUDA 换 PyTorch wheel |
| 找不到 `wav2lip.pth` | 确认已改名且在 `models/` |
| Edge 超时/失败 | 代理、DNS、或换时段；Edge 依赖在线微软服务 |
| 显存不够 | 减小 `--batch_size`；先别开 LLM / 多 session |
| 想接 LLM 对话 | `export DASHSCOPE_API_KEY=...` 后按官方 Usage 3.5；非本免费套必需 |

## 7. 和 OmniTTS 的关系

- 本套：**免费、几乎不占 TTS 显存**，适合 T4 上先跑通数字人  
- OmniTTS（Colab）：要高质量克隆时再开；启动改为 `--tts omnitts --TTS_SERVER <隧道URL>`

不需要再单独「部署 Edge-TTS 服务」——LiveTalking 进程内调用即可。
