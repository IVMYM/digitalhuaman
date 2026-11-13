# 资产与模型获取

本开源树**故意不包含**大体积权重与私人素材。以下为与代码匹配的获取指引（**需自行承担上游许可义务**）。

## LiveTalking / Wav2Lip

1. 安装 PyTorch（版本需与 GPU/CUDA 匹配；避免在未评估依赖冲突时整栈强装 CUDA 轮子）。
2. 按 [lipku/LiveTalking](https://github.com/lipku/LiveTalking) 或本仓库 `config.py` 默认，准备 `data/avatars/<avatar_id>/`（由你的源视频生成）。
3. Wav2Lip 权重与 S3FD 人脸检测权重：见 [Rudrabha/Wav2Lip](https://github.com/Rudrabha/Wav2Lip)「Getting the weights」。**非商用限制**见 `THIRD_PARTY_LICENSES.md`。
4. 典型默认形象 ID：`wav2lip256_avatar1`（须在 `data/avatars/` 中存在同名目录）。

## MuseTalk

1. 克隆上游 [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk) 并按其文档下载权重与依赖模型。
2. 在本项目中设置 `--model musetalk` 且 `avatar_id` 指向已生成的 muse 形象目录。

## Ultralight

1. 参考 [anliyuan/Ultralight-Digital-Human](https://github.com/anliyuan/Ultralight-Digital-Human) 训练或下载 checkpoint。
2. `--model ultralight`；帧率等约束见上游 README。

## fine-digital-human `static/vendor/`

快照未包含 `fine-digital-human/static/vendor/`（tasks-vision / tflite 等）。若页面功能依赖浏览器端视觉任务，需要：

- 从你所用前端栈的官方发行渠道获取与 `index.html` / `workbench.html` 引用一致的版本；或
- 暂时禁用相关 UI 功能（核心 WebRTC + `/api/offer` 路径不强制依赖 vendor 目录）。

具体文件名以你本地 `static/index.html` 脚本引用为准（公开快照中未捆绑二进制）。

## dh-admin 数据目录

首次启动会在 `dh-admin/data/`（或 `DATA_DIR`）创建 SQLite。不包含示例角色/形象二进制；在管理台 UI 中创建角色并填写 `livetalking_avatar_id`。

## TURN / ICE

WebRTC 媒体路径常需 STUN/TURN。模板：

```bash
# .secrets/turn.env（已在 .gitignore，勿提交）
TURN_USER=livetalking
TURN_PASS=<random>
TURN_PORT=3478
TURN_PUBLIC_HOST=your-reachable-host.example.com
```

可参考 `scripts/gpu-turn.sh`、`setup_coturn.sh`（**未做通用验证**）。
