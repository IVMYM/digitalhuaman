# 公开发布范围说明

本文件替代内部 `SNAPSHOT_MANIFEST.md`，描述 **digitalhuaman** 仓库所含内容与刻意排除项。

## 包含什么

- 基于 [lipku/LiveTalking](https://github.com/lipku/LiveTalking) 的数字人服务核心（`app.py`、`server/`、`avatars/` 算法源码、`tts/`、`web/` 等）
- 实验性扩展：`fine-digital-human/`（FastAPI 聚合前端）、`dh-admin/`（Vue + FastAPI 管理台）、`scripts/`（GPU/Colab 辅助）
- 文档：`README.md`、`README-EN.md`、`THIRD_PARTY_LICENSES.md`、上游只读副本 `docs/README-UPSTREAM-LIVETALKING-*.md`
- 配置文件模板：`.env.example`、`config.yaml`（示例 `avatar_id`）

## 不包含什么

- 任何真实 `.env`、`.secrets/`、Wrangler 账户缓存
- 模型权重、私人形象帧、演示 mp4、知识库文稿、生产数据库
- `node_modules/`、`dist/`、Python venv
- `fine-digital-human/static/vendor/` 大体积 wasm/tflite
- 所有 `*.bak-*` 本地备份源文件（发布前已删除）

## 脱敏

- Tailscale `tskey-*` → 占位 `tskey-auth-REPLACE_ME`
- `*.ts.net` 主机 → `YOUR-HOST.ts.net`
- 本机路径 `/Users/neo/...` → `/path/to/livetalking-muse`（部分文档/脚本）

脚本中仍可能出现历史形象代号（如 `zhengxin`），见 `scripts/README.md`；非密钥。

## 验证状态

**本 README 发行不声称** WebRTC 端到端、Colab 隧道、TURN 或数字人对话链路已在维护者环境外验证。历史有限观察见根 `README.md`。
