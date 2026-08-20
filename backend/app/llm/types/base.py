"""
基础类型定义
"""

from enum import Enum

from pydantic import BaseModel, Field


class MediaContent(BaseModel):
    """通用媒体内容"""

    url: str | None = Field(default=None, description="远程 URL")
    base64: str | None = Field(default=None, description="Base64 编码数据")
    file_path: str | None = Field(default=None, description="本地文件路径")
    asset_ref: str | None = Field(default=None, description="Scoped Asset reference")

    def has_content(self) -> bool:
        """是否有内容"""
        return any([self.url, self.base64, self.file_path])


class ImageContent(MediaContent):
    """图像内容"""

    width: int | None = Field(default=None, description="宽度")
    height: int | None = Field(default=None, description="高度")
    format: str = Field(default="png", description="图像格式 (png, jpg, webp)")


class VideoContent(MediaContent):
    """视频内容"""

    duration: float | None = Field(default=None, description="时长(秒)")
    width: int | None = Field(default=None, description="宽度")
    height: int | None = Field(default=None, description="高度")
    format: str = Field(default="mp4", description="视频格式")


class AudioContent(MediaContent):
    """音频内容"""

    duration: float | None = Field(default=None, description="时长(秒)")
    format: str = Field(default="mp3", description="音频格式 (mp3, wav, etc.)")


class ContentType(str, Enum):
    """内容类型"""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class ContentPart(BaseModel):
    """多模态消息的内容部分"""

    type: ContentType
    text: str | None = None
    image: ImageContent | None = None
    video: VideoContent | None = None
    audio: AudioContent | None = None


class Usage(BaseModel):
    """Token 使用统计"""

    prompt_tokens: int = Field(default=0, description="输入 token 数")
    completion_tokens: int = Field(default=0, description="输出 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")
    cache_read_tokens: int = Field(
        default=0, description="缓存命中 token 数（按折扣价计费）"
    )
    cache_creation_tokens: int = Field(
        default=0, description="缓存写入 token 数（Claude cache_creation）"
    )
    total_input_tokens: int = Field(
        default=0, description="缓存命中率分母：请求的全部输入 token 数"
    )


class TaskStatus(str, Enum):
    """异步任务状态 (用于视频生成等耗时任务)"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
