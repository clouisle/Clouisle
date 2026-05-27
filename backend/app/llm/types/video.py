"""
视频生成类型定义
"""

from pydantic import BaseModel, Field

from .base import ImageContent, VideoContent, TaskStatus


class AspectRatio(str):
    """常用视频宽高比"""

    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"
    RATIO_1_1 = "1:1"
    RATIO_4_3 = "4:3"
    RATIO_3_4 = "3:4"
    RATIO_21_9 = "21:9"


# ==================== Request / Response ====================


class VideoGenerationRequest(BaseModel):
    """视频生成请求"""

    prompt: str = Field(..., description="生成提示词")
    duration: float = Field(default=5.0, ge=1.0, le=30.0, description="时长(秒)")
    aspect_ratio: str = Field(default="16:9", description="宽高比")
    motion_intensity: float | None = Field(
        default=None, ge=0, le=1, description="运动强度 (0-1)"
    )
    camera_motion: str | None = Field(default=None, description="镜头运动描述")
    style: str | None = Field(default=None, description="风格")
    seed: int | None = Field(default=None, description="随机种子")
    start_image: ImageContent | None = Field(
        default=None,
        description="起始参考图像（用于支持首帧参考的视频模型）",
    )
    # 供应商特定参数
    extra_params: dict | None = Field(default=None, description="供应商特定参数")


class VideoGenerationResponse(BaseModel):
    """视频生成响应"""

    task_id: str = Field(..., description="任务 ID")
    status: TaskStatus = Field(..., description="任务状态")
    video: VideoContent | None = Field(default=None, description="生成的视频 (完成时)")
    progress: float | None = Field(default=None, ge=0, le=1, description="进度 (0-1)")
    error: str | None = Field(default=None, description="错误信息")
    model: str = Field(..., description="使用的模型")
    estimated_time: float | None = Field(default=None, description="预计剩余时间(秒)")
