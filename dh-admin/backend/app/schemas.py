from typing import Literal

from pydantic import BaseModel, Field, field_validator

AvatarType = Literal["livetalking-musetalk", "wav2lip", "ernerf", "live2d", "other"]
VoiceEngine = Literal["cosyvoice", "gpt-sovits", "edge-tts", "fish-speech", "other"]


def _http_url(value: str) -> str:
    text = value.strip()
    if not text.startswith(("http://", "https://")):
        raise ValueError("地址必须以 http:// 或 https:// 开头")
    return text.rstrip("/")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class AvatarIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: AvatarType
    livetalking_avatar_id: str = Field(default="", max_length=120)
    default_voice_id: int | None = None
    is_default: bool = False


class BrainIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    preset: str = Field(default="", max_length=40)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    model_name: str = Field(min_length=1, max_length=120)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    system_prompt: str = Field(default="", max_length=20000)
    app_id: str = Field(default="", max_length=200)
    agent_id: str = Field(default="", max_length=200)

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str) -> str:
        return _http_url(value)

    @field_validator("api_key")
    @classmethod
    def reject_mask(cls, value: str | None) -> str | None:
        if value and "••••" in value:
            raise ValueError("请填写新的 API Key，或留空以保持原密钥")
        return value


class BrainTestIn(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str | None = Field(default=None, max_length=500)
    brain_id: int | None = None

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str) -> str:
        return _http_url(value)


class VoiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    engine: VoiceEngine
    endpoint_url: str = Field(default="", max_length=500)
    voice_id: str = Field(default="", max_length=200)

    @field_validator("endpoint_url")
    @classmethod
    def check_endpoint(cls, value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        return _http_url(text)


class KnowledgeBaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)


class PersonaIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    avatar_id: int
    brain_id: int
    voice_id: int
    knowledge_base_id: int | None = None
    enabled: bool = True
    is_default: bool = False


class ChatIn(BaseModel):
    persona_id: int
    messages: list[dict] = Field(default_factory=list)


class DshExpertsIn(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    app_id: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    brain_id: int | None = None

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str) -> str:
        return _http_url(value)


class DshVerifyIn(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    app_id: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=500)
    brain_id: int | None = None
    agent_id: str = Field(default="", max_length=200)
    question: str = Field(default="你好，请用一句话介绍你自己。", min_length=1, max_length=500)

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str) -> str:
        return _http_url(value)


class SystemSettingsIn(BaseModel):
    dsw_host: str = Field(default="", max_length=200)


class RestartDisplayIn(BaseModel):
    dsw_host: str = Field(default="", max_length=200)
    target: str = Field(default="dsw", max_length=20)
