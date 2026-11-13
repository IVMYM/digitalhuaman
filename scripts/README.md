# 运维脚本说明

本目录脚本来自作者本机 GPU / Colab / DSW / Tailscale 实验环境，**非最小可复现路径的必需项**。

| 脚本族 | 用途 |
|--------|------|
| `gpu-livetalking*.sh` | 远端 GPU 上安装依赖并启动 LiveTalking |
| `gpu-turn.sh`, `setup_coturn.sh` | 用户态网络下配置 TURN（WebRTC 中继） |
| `up-xiaoxin*.sh`, `start-xiaoxin.sh`, `gpu-matte-*.sh` | **历史人设专用**部署流（脚本名与注释中的 `zhengxin`/`xiaoxin` 为本地形象代号；请改为你自己的 `avatar_id` 与资源路径） |
| `deploy-fine-digital-human.sh` | 部署 fine-digital-human 辅助 |

公开快照已脱敏 Tailscale 主机名与 auth key 占位符。运行前请阅读脚本内变量（`GPU_HOST`、`GPU_REPO` 等）并替换为你的环境。

**未验证声明**：仓库维护者仅在 2026-11-03/04 对部分 Colab 路径做过有限试验（见根 `README.md`「历史观察」），不保证这些脚本在你环境中可直接成功。
