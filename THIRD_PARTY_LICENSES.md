# 第三方许可与模型限制

**本仓库根目录 `LICENSE` 仅适用于 [lipku/LiveTalking](https://github.com/lipku/LiveTalking) 来源及在相同 Apache-2.0 条款下贡献的封装代码。**  
以下 vendored 子树与模型_weights_另有独立许可或商用限制；**不得**因根目录 Apache-2.0 而推定可 unrestricted 商用。

## 汇总表

| 组件 | 仓库内路径 | 上游 | 许可 / 限制 |
|------|------------|------|-------------|
| LiveTalking 核心 | `app.py`, `server/`, `tts/`, `web/` 等 | [lipku/LiveTalking](https://github.com/lipku/LiveTalking) | Apache-2.0（见 `LICENSE`） |
| Wav2Lip 推理代码 | `avatars/wav2lip/` | [Rudrabha/Wav2Lip](https://github.com/Rudrabha/Wav2Lip) | **个人 / 学术 / 非商用**；商用须联系上游 |
| Wav2Lip 预训练权重 | 未随仓库分发 | Google Drive 等（见上游 README） | 与 LRS2 训练数据相关，**非商用** |
| face_alignment / S3FD | `avatars/wav2lip/face_detection/`, musetalk 内 face 代码 | [1adrianb/face-alignment](https://github.com/1adrianb/face-alignment) 等 | BSD-3-Clause（face-alignment）；权重须单独下载 |
| MuseTalk 相关 | `avatars/musetalk/` | [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk) | **MIT**（源码）；内含 Whisper 等 MIT 依赖说明见上游 `LICENSE` |
| OpenAI Whisper（vendored 词表/代码） | `avatars/musetalk/whisper/` | [openai/whisper](https://github.com/openai/whisper) | MIT |
| Ultralight | `avatars/ultralight/` | [anliyuan/Ultralight-Digital-Human](https://github.com/anliyuan/Ultralight-Digital-Human) | Apache-2.0（见上游） |
| Ultralight / Wenet 权重 | 未随仓库分发 | Google Drive 等 | 遵循各自上游分发条款 |
| sd-vae-ft-mse 等（MuseTalk 推理用） | 未随仓库分发 | Hugging Face | 多为 MIT（见 MuseTalk `LICENSE`） |

## Wav2Lip（非商用要点）

上游 [Wav2Lip README](https://github.com/Rudrabha/Wav2Lip) 明示：

> This repository can only be used for personal/research/non-commercial purposes. … any form of **commercial use is strictly prohibited**.

本仓库保留 Wav2Lip **源代码**以便与 LiveTalking 集成实验；**不**随仓库分发 Wav2Lip 检查点。使用预训练权重前请阅读上游条款。

## MuseTalk

上游 `LICENSE` 为 MIT。注意 MuseTalk 文档列出的额外依赖（DWPose Apache-2.0、face-parsing MIT 等）及 **需单独下载的模型权重**。

## 本发行版未包含的内容

- `models/`、`.pth` / `.onnx` / 形象帧包 / 私人音视频
- `fine-digital-human/static/vendor/`（约 34MB wasm/tflite）
- 私人知识库、SQLite 业务数据

获取方式见 [docs/ASSETS_AND_MODELS.md](./docs/ASSETS_AND_MODELS.md)。

## 商标与名称

`LiveTalking` 等为上游项目标识。本 GitHub 仓库名 **digitalhuaman** 为发布者选用，与上游无隶属关系。
