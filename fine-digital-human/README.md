# fine-digital-human

浏览器端 MVP：语音/文字输入 → LLM（经 dh-admin 或直连）→ TTS → LiveTalking WebRTC 口型驱动。

## 启动

```bash
cd fine-digital-human
cp .env.example .env   # 按需修改
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。

## 默认假设

- `LIVETALKING_URL` 指向 LiveTalking（默认 `http://127.0.0.1:8010`）。
- 可选 `DH_ADMIN_*`：从管理台拉取默认角色、形象 ID、背景图 URL。
- 可选 `MOSS_BASE_URL` / `TTS_URL`：替换对话或 TTS 后端（见 `.env.example`）。

形象 ID 默认 `wav2lip256_avatar1`（须与本机 `data/avatars/` 中已生成的目录名一致）。

背景图：将 PNG 放入 `static/backgrounds/`，设置 `DIGITAL_HUMAN_BACKGROUND_URL=/backgrounds/your.png`。

## WebRTC / TURN

页面会读取仓库根目录 `.secrets/turn.env`（勿提交）或 `TURN_ENV_FILE`，向浏览器下发 ICE。未配置时可能仅 STUN，复杂网络下需自建 TURN（见根目录 `scripts/gpu-turn.sh`）。

## 前端 vendor 资源

本仓库**不包含** `static/vendor/` 下的大体积 wasm/tflite（见根目录 `docs/ASSETS_AND_MODELS.md`）。抠图/视觉特性在缺少 vendor 时可能不可用；核心 WebRTC 对话路径不依赖这些文件。
