"""
音频类型定义 (TTS / STT)
"""

from enum import Enum
from pydantic import BaseModel, Field

from .base import AudioContent, ImageContent


class TTSVoice(str, Enum):
    """OpenAI TTS 预设声音"""

    ALLOY = "alloy"
    ECHO = "echo"
    FABLE = "fable"
    ONYX = "onyx"
    NOVA = "nova"
    SHIMMER = "shimmer"


class AudioFormat(str, Enum):
    """音频格式"""

    MP3 = "mp3"
    WAV = "wav"
    OPUS = "opus"
    AAC = "aac"
    FLAC = "flac"
    PCM = "pcm"


# ==================== TTS ====================


class TTSRequest(BaseModel):
    """语音合成请求"""

    text: str = Field(..., description="要合成的文本")
    voice: str | None = Field(default=None, description="声音名称")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="语速")
    format: str = Field(default="mp3", description="输出格式")


class TTSResponse(BaseModel):
    """语音合成响应"""

    audio: AudioContent = Field(..., description="生成的音频")
    model: str = Field(..., description="使用的模型")


# ==================== Audio generation ====================


class AudioGenerationRequest(BaseModel):
    """Prompt-driven audio generation request."""

    prompt: str = Field(..., min_length=1, description="Audio generation prompt")
    image: ImageContent | None = Field(
        default=None, description="Optional reference image"
    )
    audio_references: list[AudioContent] = Field(
        default_factory=list,
        max_length=3,
        description="Optional reference audio clips",
    )
    format: str = Field(default="mp3", description="Output audio format")
    extra_params: dict = Field(default_factory=dict, description="Provider options")


class AudioGenerationResponse(BaseModel):
    """Prompt-driven audio generation response."""

    audio: AudioContent = Field(..., description="Generated audio")
    model: str = Field(..., description="Effective model or resource ID")


# ==================== STT ====================


class STTRequest(BaseModel):
    """语音识别请求"""

    audio: AudioContent = Field(..., description="输入音频")
    language: str | None = Field(default=None, description="语言代码 (如 'en', 'zh')")
    prompt: str | None = Field(default=None, description="上下文提示")
    response_format: str = Field(default="text", description="响应格式")
    timestamp_granularities: list[str] | None = Field(
        default=None, description="时间戳粒度 ['word', 'segment']"
    )


class TranscriptionSegment(BaseModel):
    """转录片段"""

    id: int = Field(..., description="片段 ID")
    start: float = Field(..., description="开始时间(秒)")
    end: float = Field(..., description="结束时间(秒)")
    text: str = Field(..., description="文本内容")


class TranscriptionWord(BaseModel):
    """转录单词"""

    word: str = Field(..., description="单词")
    start: float = Field(..., description="开始时间(秒)")
    end: float = Field(..., description="结束时间(秒)")


class STTResponse(BaseModel):
    """语音识别响应"""

    text: str = Field(..., description="识别文本")
    language: str | None = Field(default=None, description="检测到的语言")
    duration: float | None = Field(default=None, description="音频时长(秒)")
    segments: list[TranscriptionSegment] | None = Field(
        default=None, description="时间戳片段"
    )
    words: list[TranscriptionWord] | None = Field(
        default=None, description="单词级时间戳"
    )
    model: str = Field(..., description="使用的模型")
