# 数字人管理后台

给私有部署的数字人准备的管理后台。它跑在一台小的 CPU VPS 上，用来管形象、大脑（OpenAI 兼容大模型）、声音、知识库和角色，并提供给 GPU 上的 [LiveTalking](https://github.com/lipku/LiveTalking) 调用的接口。

口型推理、推流、TTS 仍在 GPU 服务器上。这台机器没有显卡也能用：可以登录、改配置、用「对话测试」直接打所选角色的大脑。

## 功能

- 单个管理员账号。首次启动用 `.env` 里的用户名和密码创建，密码用 bcrypt 保存，登录发 JWT。之后在「设置」里改密码，重启不会覆盖。
- 形象、大脑、声音、角色、知识库的增删改。
- 大脑的 API Key 用 `ENCRYPTION_KEY` 加密后入库，管理接口只返回掩码。
- 大脑可以测试连接，并带 Ollama、vLLM、DeepSeek、通义千问、OpenAI 的预设。
- 对话测试走 SSE，使用角色的系统提示词；如果挂了知识库，会附上一段检索结果。
- 运行时接口：`GET /api/runtime/personas/{id}` 返回拼好的配置（含解密后的 Key），用单独的 `RUNTIME_API_TOKEN` 保护。
- OpenAI 兼容代理：`POST /v1/chat/completions`。LiveTalking 把 LLM 地址指到这里后，换大脑只改后台，不用改 GPU 上的 Key。

知识库检索目前是关键词重叠，不是向量检索。接口在 `backend/app/services/retrieval.py`，里面有接 RAGFlow 的 TODO。默认不安装 torch 一类重依赖。

## 在 VPS 上部署

目标环境：Ubuntu 24.04，宿主机 nginx 已经占用 80/443。本服务只绑定 `127.0.0.1:18200`，容器内存限制默认 512MB，一个 uvicorn 进程同时提供 API 和构建好的前端。默认 SQLite，数据在 `./data`。

内存很紧时（可用内存经常低于 1GB，或者 swap 已经很高），`docker compose build` 里的 Node 构建可能失败。先停掉暂时不用的容器，或在另一台机器构建镜像再 `docker save` / `docker load`。

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
# 重新登录后 docker 才对当前用户生效

git clone <你的仓库地址>
cd <仓库目录>
cp .env.example .env
```

编辑 `.env`，至少换掉这些值：

```bash
openssl rand -hex 32    # JWT_SECRET
openssl rand -hex 32    # ENCRYPTION_KEY，任意长随机串即可
openssl rand -hex 24    # RUNTIME_API_TOKEN
# ADMIN_PASSWORD 设一个至少 8 位的密码
```

然后：

```bash
chmod +x deploy.sh
./deploy.sh
```

等价命令是 `docker compose up -d --build`。`deploy.sh` 会在 `.env` 仍含 `please-change-me` 时拒绝启动。

浏览器访问 `http://127.0.0.1:18200`（只在 VPS 本机）。查看状态：

```bash
docker compose ps
docker compose logs -f admin
curl -s http://127.0.0.1:18200/api/health
```

更新代码后重新构建：

```bash
git pull
docker compose up -d --build
```

### Nginx

示例在 `nginx.example.conf`。用一个单独的域名反代到 `http://127.0.0.1:18200`，不要挂在子路径，否则前端资源路径会错。对话是 SSE，`proxy_buffering` 和 gzip 都要关掉，并加大 `proxy_read_timeout` 和 `client_max_body_size`。

改完执行 `sudo nginx -t && sudo systemctl reload nginx`。

GPU 服务器在另一台机器上时，它访问的是这个 HTTPS 域名，不是 `127.0.0.1:18200`。不要为了图省事把端口改成 `0.0.0.0` 暴露到公网；运行时接口会返回解密后的模型 Key。

Ollama 或 vLLM 如果跑在同一台 VPS 的宿主机上，容器里的 `127.0.0.1` 指的是容器自己。compose 已经加了 `host.docker.internal`，大脑的 Base URL 写成 `http://host.docker.internal:11434/v1`。

国内拉镜像慢时，可以：

```bash
docker compose build \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
docker compose up -d
```

## 接到 LiveTalking

当前 LiveTalking 的 `llm.py` 只内置了 `dashscope` 和 `orcarouter`。在 GPU 机器的 `llm.py` 里给 `LLM_PROVIDERS` 加一项，让它把 OpenAI 兼容请求打到这个后台：

```python
"dh-admin": {
    "api_key_env": "DH_ADMIN_RUNTIME_TOKEN",
    "base_url": "https://dh-admin.example.com/v1",
    "default_model": "展厅讲解员",
},
```

`default_model` 填后台里的角色名。代理会按这个名字找到角色，再用该角色大脑里配置的真实模型名去请求上游。角色名对不上时，使用「启用且标为默认」的角色。

```bash
export DH_ADMIN_RUNTIME_TOKEN='与 VPS 上 RUNTIME_API_TOKEN 相同'
python app.py --transport webrtc --model wav2lip \
  --avatar_id wav2lip256_avatar1 \
  --tts edgetts --REF_FILE zh-CN-YunxiaNeural \
  --llm_provider dh-admin --llm_model "展厅讲解员"
```

也可以把同样的字段写进 LiveTalking 的 `config.yaml`（`llm_provider`、`llm_model`、`avatar_id`、`tts`、`REF_FILE`、`TTS_SERVER`）。

这样 GPU 上只保存运行时令牌。在后台把角色换到另一个大脑后，下一次对话就会走新的上游，不用把 DeepSeek 或通义的 Key 再抄到 GPU 上。

形象和声音不会自动同步：

1. 在 GPU 上用 LiveTalking 的 `genavatar` 从视频生成形象，得到 `data/avatars/<avatar_id>`。
2. 后台「形象管理」里的 `avatar_id` 填这个目录名。源视频可以留一份在本后台，方便自己归档。
3. TTS 仍由 LiveTalking 的 `--tts`、`--REF_FILE`、`--TTS_SERVER` 决定。后台的声音配置用于记录，并出现在运行时接口里，方便以后写自动下发。

直接看某个角色的完整配置（含解密后的 Key，请只在内网或 HTTPS 后使用）：

```bash
curl -sS -H "Authorization: Bearer $RUNTIME_API_TOKEN" \
  http://127.0.0.1:18200/api/runtime/personas/1
```

也可以用头 `X-Runtime-Token`。角色列表（不含 Key）：`GET /api/runtime/personas`。

OpenAI 兼容调用示例：

```bash
curl -sS http://127.0.0.1:18200/v1/chat/completions \
  -H "Authorization: Bearer $RUNTIME_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"展厅讲解员","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

角色名放在 JSON 的 `model` 里，可以是中文。请求头 `X-Persona-Id` 用来传数字 id（HTTP 头不适合中文）。`stream: true` 时按上游的 SSE 原样转发。

## 本地开发

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cd ..
cp .env.example .env
# 改掉 please-change-me，并把 DATA_DIR 留成 ./data

cd backend
uvicorn app.main:app --reload --port 18200
```

另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器在 `http://127.0.0.1:5174`，把 `/api` 和 `/v1` 代理到 18200。生产环境不需要单独的前端进程，镜像里已经把 `vite build` 的结果交给 FastAPI。

## 测试

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

覆盖登录、改密、形象/大脑/声音/角色/知识库、密钥加密与掩码、运行时令牌，以及 mock 上游后的 `/v1/chat/completions` 和对话 SSE。

## 数据

- SQLite 文件：`data/app.db`（容器内 `/data/app.db`）
- 上传：`data/uploads/`
- 已开启 WAL。备份时不要直接拷正在写的库文件：

```bash
docker compose exec admin python -c "import sqlite3; s=sqlite3.connect('/data/app.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close(); s.close()"
```

换 `ENCRYPTION_KEY` 之后，已保存的 API Key 无法解密，需要在后台重新填写。

换 Postgres 时设置 `DATABASE_URL=postgresql+psycopg://...` 后重建容器。启动时只会 `create_all`，不会把 SQLite 里的旧数据迁过去。镜像里带了驱动，compose 默认不启 Postgres 容器。

## 还没做的部分

- 知识库不是 RAG。`KeywordRetriever.retrieve` 可以换成 RAGFlow 的 HTTP 调用，不要把 embedding 模型装进这个 512MB 容器。
- 不推送形象文件，也不远程调用 LiveTalking 的会话、打断和推流接口。
- 只有一个管理员，没有多用户。
- 管理端对话测试只验证大脑回复，不合成语音、不渲染口型。
