"""
图像生成类型定义
"""

from enum import Enum
from pydantic import BaseModel, Field

from .base import ImageContent


class ImageSize(str, Enum):
    """常用图像尺寸"""

    S_256 = "256x256"
    S_512 = "512x512"
    S_1024 = "1024x1024"
    S_1792_1024 = "1792x1024"  # DALL-E 3 横向
    S_1024_1792 = "1024x1792"  # DALL-E 3 纵向


class ImageStyle(str, Enum):
    """图像风格 (DALL-E 3)"""

    VIVID = "vivid"
    NATURAL = "natural"


class ImageQuality(str, Enum):
    """图像质量 (DALL-E 3)"""

    STANDARD = "standard"
    HD = "hd"


# ==================== Request / Response ====================


class ImageGenerationRequest(BaseModel):
    """图像生成请求"""

    prompt: str = Field(..., description="生成提示词")
    negative_prompt: str | None = Field(default=None, description="负面提示词")
    width: int = Field(default=1024, ge=256, le=4096, description="宽度")
    height: int = Field(default=1024, ge=256, le=4096, description="高度")
    num_images: int = Field(default=1, ge=1, le=10, description="生成数量")
    style: str | None = Field(default=None, description="风格")
    quality: str | None = Field(default=None, description="质量")
    seed: int | None = Field(default=None, description="随机种子")
    images: list[ImageContent] | None = Field(
        default=None,
        description="参考图像列表（用于编辑或带参考图的生成）",
    )
    extra_params: dict | None = Field(default=None, description="供应商特定参数")


class GeneratedImage(BaseModel):
    """生成的图像"""

    image: ImageContent = Field(..., description="图像内容")
    revised_prompt: str | None = Field(default=None, description="修订后的提示词")
    seed: int | None = Field(default=None, description="实际使用的种子")


class ImageGenerationResponse(BaseModel):
    """图像生成响应"""

    images: list[GeneratedImage] = Field(..., description="生成的图像列表")
    model: str = Field(..., description="使用的模型")
