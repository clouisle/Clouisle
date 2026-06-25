from pydantic import BaseModel


class CaptchaResponse(BaseModel):
    """验证码响应"""

    captcha_id: str
    challenge: str
    prompt: str = "captcha_click_prompt"
    expires_in: int = 300


class CaptchaVerifyRequest(BaseModel):
    """验证码验证请求"""

    captcha_id: str
    token: str
