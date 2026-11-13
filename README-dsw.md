# LiveTalking · 阿里云 DSW

Colab 仍用 `scripts/up-xiaoxin.sh`。DSW 用本文件里的命令。权重和 Python 包在 NAS `/mnt/workspace/livetalking`，实例重启后从这里恢复，不再访问 PyTorch 官网和 hf-mirror。

前提：DSW 已开机，Tailscale 上有在线的 `colab-livetalking*` 节点。

## 只重启 LiveTalking

环境还在、只是页面断了或进程停了时，在 DSW 上执行：

```bash
bash /content/livetalking/LiveTalking/scripts/gpu-livetalking-dsw.sh start
```

先停掉占用 8010 的旧进程，再用形象 `zhengxin` 拉起。日志：`/tmp/livetalking_app.log`。

## 实例重启后的最快启动

系统盘会回到镜像，`/content` 和后装的包都会没。在本机仓库执行：

```bash
scripts/up-xiaoxin-dsw.sh
```

这条命令会：

1. 同步代码。镜像里没有 `rsync` 时先用 apt 装上。
2. `prepare`：从 NAS 装回 `torch 2.11.0+cu128` 和 Python 依赖，拷回 `wav2lip.pth`、`s3fd.pth`，以及郑欣的 145 帧。
3. 启动 TURN，再启动 LiveTalking `:8010`。
4. 部署 HTTPS 页面 `:8000`，并检查页面、TURN 和抠图。

本机如果还有 `assets/avatars/zhengxin/`，会再传一次这 34 MB，用来跳过抠图。不要设 `FORCE_MATTE=1`，否则会重新抠图。

页面：`https://<这台机器的 Tailscale 名>:8000/`

## 浏览器断开时的日志

关掉页面或 WebRTC 断开后，日志末尾是这样的，这是会话结束，不是进程崩溃：

```text
Connection state is closed
Removing session ...
baseavatar render thread stop
baseavatar inference thread stop
baseavatar process_frames thread stop
ttsreal thread stop
```

`:8010` 的服务还在。重新打开页面即可。若端口已经没了，再用上面的 `start`。

推理大约 125 fps、播出 25 fps 是正常的。生成比播放快时，脚本会把缓冲压在大约 200 ms，避免丢音频包把语速快进。

## NAS 里有什么

`/mnt/workspace/livetalking`，大约 5.1 GB。

| 路径 | 内容 |
|---|---|
| `wheels/torch-cu128.tar.gz` | `torch 2.11.0+cu128`（cp312） |
| `wheels/pip/` | CUDA 12 运行库、torchvision、torchaudio、triton，以及 LiveTalking / 页面 / 抠图的 Python wheel |
| `models/wav2lip.pth` | Wav2Lip 权重 |
| `models/s3fd.pth` | 人脸检测权重 |
| `avatars/zhengxin/` | 抠好的郑欣，145 帧 |

`ffmpeg` 和 `rsync` 很小，仍用 apt 安装。`silueta.onnx` 目前不在 NAS 上；下次重新抠图时会下载并写进 `models/`。
