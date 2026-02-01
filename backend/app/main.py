import json
import logging
import time
import traceback

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from tortoise.contrib.fastapi import register_tortoise

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.init_data import init_db
from app.core.i18n import set_language, t, get_code_message
from app.core.redis import close_redis
from app.schemas.response import success, error, ResponseCode, BusinessError

# Import celery app to ensure tasks are bound correctly when API sends tasks
from app.core.celery import celery_app  # noqa: F401

# Register builtin tools
from app.llm.tools.builtin import register_all_builtin_tools

register_all_builtin_tools()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)


# 自定义验证错误处理器
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    将 Pydantic 验证错误转换为统一响应格式，并返回字段级别的错误
    """
    errors: dict[str, list[str]] = {}
    for err in exc.errors():
        # loc 是一个 tuple，如 ('body', 'email') 或 ('body', 'user', 'email')
        loc = err.get("loc", ())
        # 跳过 'body' 前缀，获取字段名
        field_parts = [str(part) for part in loc if part != "body"]
        field = ".".join(field_parts) if field_parts else "unknown"

        # 获取错误消息
        msg = err.get("msg", "Invalid value")

        # 如果同一字段有多个错误，用列表存储
        if field not in errors:
            errors[field] = []
        errors[field].append(msg)

    return JSONResponse(
        status_code=422,
        content=error(
            code=ResponseCode.VALIDATION_ERROR,
            msg=t("validation_error"),
            data={"errors": errors},
        ),
    )


# 自定义业务异常处理器
@app.exception_handler(BusinessError)
async def business_exception_handler(request: Request, exc: BusinessError):
    """
    将 BusinessError 转换为统一响应格式
    """
    # 获取消息
    if exc.msg:
        msg = exc.msg
    elif exc.msg_key:
        msg = t(exc.msg_key, **exc.kwargs)
    elif isinstance(exc.code, ResponseCode):
        msg = get_code_message(exc.code)
    else:
        msg = t("unknown_error")

    return JSONResponse(
        status_code=exc.status_code,
        content=error(
            code=exc.code,
            msg=msg,
            data=exc.data,
        ),
    )


# 自定义 HTTP 异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    将 HTTPException 转换为统一响应格式
    """
    # 根据状态码映射到响应码
    code_map = {
        400: ResponseCode.UNKNOWN_ERROR,
        401: ResponseCode.UNAUTHORIZED,
        403: ResponseCode.PERMISSION_DENIED,
        404: ResponseCode.NOT_FOUND,
    }
    response_code = code_map.get(exc.status_code, ResponseCode.UNKNOWN_ERROR)

    return JSONResponse(
        status_code=exc.status_code,
        content=error(
            code=response_code,
            msg=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        ),
    )


# Logging middleware to log request and response
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 获取请求信息
        method = request.method
        url = str(request.url)
        client_ip = request.client.host if request.client else "unknown"

        # 读取请求体（只对 POST/PUT/PATCH 请求）
        request_body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    content_type = request.headers.get("content-type", "")
                    if "application/json" in content_type:
                        request_body = json.loads(body_bytes.decode("utf-8"))
                        # 隐藏敏感字段
                        if isinstance(request_body, dict):
                            request_body = {
                                k: "***" if k in ["password", "token", "secret"] else v
                                for k, v in request_body.items()
                            }
                    elif "form" in content_type:
                        request_body = "<form-data>"
            except Exception:
                request_body = "<parse-error>"

        # 打印请求日志
        logger.info(f">>> {method} {url} | IP: {client_ip}")
        if request_body:
            logger.info(
                f"    Request Body: {json.dumps(request_body, ensure_ascii=False)}"
            )

        # 处理请求
        try:
            response = await call_next(request)

            # 计算耗时
            duration = time.time() - start_time

            # 对于错误响应（4xx, 5xx），读取并打印响应内容
            response_body = None
            if response.status_code >= 400:
                # 读取响应体
                response_body_bytes = b""
                async for chunk in response.body_iterator:
                    response_body_bytes += chunk

                try:
                    response_body = json.loads(response_body_bytes.decode("utf-8"))
                except Exception:
                    response_body = response_body_bytes.decode(
                        "utf-8", errors="replace"
                    )

                # 重新创建响应（因为body_iterator已被消费）
                from starlette.responses import Response as StarletteResponse

                response = StarletteResponse(
                    content=response_body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            # 打印响应日志
            if response.status_code >= 400:
                logger.warning(
                    f"<<< {method} {url} | Status: {response.status_code} | Duration: {duration:.3f}s"
                )
                if response_body:
                    logger.warning(
                        f"    Response Body: {json.dumps(response_body, ensure_ascii=False) if isinstance(response_body, (dict, list)) else response_body}"
                    )
            else:
                logger.info(
                    f"<<< {method} {url} | Status: {response.status_code} | Duration: {duration:.3f}s"
                )

            return response

        except Exception as e:
            # 计算耗时
            duration = time.time() - start_time

            # 打印错误日志
            logger.error(f"<<< {method} {url} | Error | Duration: {duration:.3f}s")
            logger.error(f"    Exception: {str(e)}")
            logger.error(f"    Traceback:\n{traceback.format_exc()}")

            # 返回错误响应
            return JSONResponse(
                status_code=500,
                content={"code": -1, "data": None, "msg": "Internal Server Error"},
            )


# Language middleware to set language from Accept-Language header
class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get language from Accept-Language header or X-Language header
        lang = request.headers.get("X-Language") or request.headers.get(
            "Accept-Language", "en"
        )
        # Parse Accept-Language (e.g., "zh-CN,zh;q=0.9,en;q=0.8" -> "zh")
        lang = lang.split(",")[0].split(";")[0].strip()
        set_language(lang)
        response = await call_next(request)
        return response


# Set all CORS enabled origins (must be added before other middlewares)
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(LanguageMiddleware)
app.add_middleware(LoggingMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return success(msg="Welcome to Clouisle API")


# Pre-register hook to run migrations before Tortoise generates schemas
@app.on_event("startup")
async def pre_tortoise_init():
    """Run database migrations before Tortoise initializes schemas"""
    from tortoise import Tortoise

    # Initialize Tortoise connection (without generating schemas yet)
    await Tortoise.init(
        db_url=settings.DATABASE_URL
        or f"postgres://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
        modules={"models": ["app.models"]},
    )

    # Run migrations BEFORE generating schemas
    from app.core.init_data import init_agent_tools_credentials, fix_cascade_delete_policies
    try:
        await init_agent_tools_credentials()
    except Exception as e:
        logger.warning(f"Agent tools_credentials migration failed: {e}")

    try:
        await fix_cascade_delete_policies()
    except Exception as e:
        logger.warning(f"CASCADE delete policies migration failed: {e}")

    # Now generate schemas (this will validate against the updated database)
    await Tortoise.generate_schemas()


# Register Tortoise (but skip generate_schemas since we did it manually above)
register_tortoise(
    app,
    db_url=settings.DATABASE_URL
    or f"postgres://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
    modules={"models": ["app.models"]},
    generate_schemas=False,  # Changed to False - we handle it manually in pre_tortoise_init
    add_exception_handlers=True,
)


@app.on_event("startup")
async def startup_event():
    try:
        await init_db()
    except Exception as e:
        print(f"Error seeding data: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    await close_redis()
