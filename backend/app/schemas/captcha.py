from pydantic import BaseModel


class CaptchaResponse(BaseModel):
    """验证码响应"""

    captcha_id: str
    challenge: str
    prompt: str = "captcha_click_prompt"
    expires_in: int = 300


class CaptchaClickRequest(BaseModel):
    """点击式验证码证明请求"""

    captcha_id: str
    challenge: str
    click_nonce: str
    elapsed_ms: int


class CaptchaProofResponse(BaseModel):
    """点击式验证码证明响应"""

    captcha_id: str
    captcha_token: str


class CaptchaVerifyRequest(BaseModel):
    """验证码验证请求"""

    captcha_id: str
    token: str
