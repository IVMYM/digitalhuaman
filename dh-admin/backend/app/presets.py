PRESETS = [
    {
        "id": "ollama",
        "name": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model_name": "qwen2.5:7b",
        "hint": "本机或内网 Ollama，多数情况不需要 API Key。后台跑在 Docker 里、Ollama 在宿主机上时，把 127.0.0.1 换成 host.docker.internal。",
    },
    {
        "id": "vllm",
        "name": "vLLM",
        "base_url": "http://127.0.0.1:8000/v1",
        "model_name": "Qwen/Qwen2.5-7B-Instruct",
        "hint": "vLLM 的 OpenAI 兼容端口。若开启了鉴权，再填写 API Key。",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
        "hint": "需要 DeepSeek 的 API Key。",
    },
    {
        "id": "qwen",
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
        "hint": "阿里云 DashScope 兼容模式，填写 DASHSCOPE_API_KEY。",
    },
    {
        "id": "dsh",
        "name": "DeepSeek Harness 专家",
        "base_url": "https://www.datafine.cn/onechat/dsh",
        "model_name": "",
        "hint": "datafine OneChat 的专家大脑。填 App ID 和 App Secret，再从已授权专家里选一个；密钥即 App Secret，加密存本机。",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
        "hint": "OpenAI 官方接口。",
    },
]

# LiveTalking config.py 里的 --tts 取值
TTS_FLAG = {
    "edge-tts": "edgetts",
    "gpt-sovits": "gpt-sovits",
    "cosyvoice": "cosyvoice",
    "fish-speech": "fishtts",
    "other": "",
}
