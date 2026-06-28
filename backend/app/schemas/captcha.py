from pydantic import BaseModel, Field


class CaptchaResponse(BaseModel):
    """验证码响应"""

    captcha_id: str
    challenge: str
    prompt: str = "captcha_click_prompt"
    expires_in: int = 300


class CaptchaPointerPoint(BaseModel):
    """点击式验证码指针轨迹点"""

    x: float
    y: float
    t: int
    event: str = "move"


class CaptchaClickRequest(BaseModel):
    """点击式验证码证明请求"""

    captcha_id: str
    challenge: str
    clicked_option: str
    elapsed_ms: int
    pointer: list[CaptchaPointerPoint] = Field(default_factory=list)


class CaptchaProofResponse(BaseModel):
    """点击式验证码证明响应"""

    captcha_id: str
    captcha_token: str


class CaptchaVerifyRequest(BaseModel):
    """验证码验证请求"""

    captcha_id: str
    token: str
