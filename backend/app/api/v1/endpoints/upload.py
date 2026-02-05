"""
通用文件上传接口
"""

import os
import uuid
import hashlib
import aiofiles
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api import deps
from app.models.user import User
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.services.file_parser import (
    file_parser_service,
    FileParseConfig,
)

router = APIRouter()

# 上传配置
# 统一使用项目根目录的 uploads/ 文件夹
UPLOAD_DIR = os.path.join(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        )
    ),
    "uploads",
)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
}
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/csv",
    "application/json",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# 文件类型到扩展名映射
MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


def get_file_hash(content: bytes) -> str:
    """计算文件 MD5 哈希"""
    return hashlib.md5(content).hexdigest()


def get_upload_path(category: str, filename: str) -> str:
    """获取上传路径，按日期和类别组织"""
    date_path = datetime.now().strftime("%Y/%m")
    return os.path.join(UPLOAD_DIR, category, date_path, filename)


def get_file_url(category: str, date_path: str, filename: str) -> str:
    """生成文件访问 URL"""
    return f"/api/v1/upload/files/{category}/{date_path}/{filename}"


@router.post("/image", response_model=Response[dict])
async def upload_image(
    file: UploadFile = File(...),
    category: str = Query("general", description="文件分类：general, avatar, icon 等"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    上传图片文件

    - 支持格式：JPEG, PNG, GIF, WebP, SVG, ICO
    - 最大大小：10MB
    - 返回文件 URL
    """
    # 验证文件类型
    content_type = file.content_type
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="invalid_file_type",
            data={"allowed": list(ALLOWED_IMAGE_TYPES)},
        )

    # 读取文件内容
    content = await file.read()

    # 验证文件大小
    if len(content) > MAX_FILE_SIZE:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_too_large",
            data={"max_size": MAX_FILE_SIZE},
        )

    # 生成唯一文件名
    file_hash = get_file_hash(content)[:8]
    ext = MIME_TO_EXT.get(
        content_type, os.path.splitext(file.filename or "")[1] or ".bin"
    )
    unique_filename = f"{uuid.uuid4().hex[:12]}_{file_hash}{ext}"

    # 获取保存路径
    date_path = datetime.now().strftime("%Y/%m")
    save_dir = os.path.join(UPLOAD_DIR, category, date_path)
    save_path = os.path.join(save_dir, unique_filename)

    # 确保目录存在
    os.makedirs(save_dir, exist_ok=True)

    # 保存文件
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # 生成访问 URL
    file_url = f"/api/v1/upload/files/{category}/{date_path}/{unique_filename}"

    return success(
        data={
            "url": file_url,
            "filename": unique_filename,
            "original_name": file.filename,
            "size": len(content),
            "content_type": content_type,
        },
        msg_key="file_uploaded",
    )


@router.post("/file", response_model=Response[dict])
async def upload_file(
    file: UploadFile = File(...),
    category: str = Query("general", description="文件分类"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    上传通用文件

    - 支持格式：图片、PDF、文本文档
    - 最大大小：10MB
    """
    content_type = file.content_type
    allowed_types = ALLOWED_IMAGE_TYPES | ALLOWED_DOCUMENT_TYPES

    if content_type not in allowed_types:
        filename = file.filename or ""
        if filename and file_parser_service.is_supported(filename):
            content_type = file_parser_service.get_mime_type(filename)

    if content_type not in allowed_types:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="invalid_file_type",
            data={"allowed": list(allowed_types)},
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_too_large",
            data={"max_size": MAX_FILE_SIZE},
        )

    file_hash = get_file_hash(content)[:8]
    ext = MIME_TO_EXT.get(
        content_type, os.path.splitext(file.filename or "")[1] or ".bin"
    )
    unique_filename = f"{uuid.uuid4().hex[:12]}_{file_hash}{ext}"

    date_path = datetime.now().strftime("%Y/%m")
    save_dir = os.path.join(UPLOAD_DIR, category, date_path)
    save_path = os.path.join(save_dir, unique_filename)

    os.makedirs(save_dir, exist_ok=True)

    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    file_url = f"/api/v1/upload/files/{category}/{date_path}/{unique_filename}"

    return success(
        data={
            "url": file_url,
            "filename": unique_filename,
            "original_name": file.filename,
            "size": len(content),
            "content_type": content_type,
        },
        msg_key="file_uploaded",
    )


@router.get("/files/{category}/{year}/{month}/{filename}")
async def get_file(
    category: str,
    year: str,
    month: str,
    filename: str,
) -> Any:
    """
    获取上传的文件（公开访问）
    """
    file_path = os.path.join(UPLOAD_DIR, category, year, month, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # 安全检查：确保路径在 UPLOAD_DIR 内
    real_path = os.path.realpath(file_path)
    real_upload_dir = os.path.realpath(UPLOAD_DIR)
    if not real_path.startswith(real_upload_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(file_path)


@router.delete(
    "/files/{category}/{year}/{month}/{filename}", response_model=Response[None]
)
async def delete_file(
    category: str,
    year: str,
    month: str,
    filename: str,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    删除上传的文件（仅管理员）
    """
    file_path = os.path.join(UPLOAD_DIR, category, year, month, filename)

    # 安全检查
    real_path = os.path.realpath(file_path)
    real_upload_dir = os.path.realpath(UPLOAD_DIR)
    if not real_path.startswith(real_upload_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(file_path):
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="file_not_found",
        )

    os.remove(file_path)

    return success(msg_key="file_deleted")


# ============ File Parsing Endpoints ============


class FileParseRequest(BaseModel):
    """Request for file parsing configuration"""

    max_content_length: int = Field(
        default=100000,
        ge=1000,
        le=500000,
        description="Maximum content length in characters",
    )
    truncate_strategy: str = Field(
        default="end",
        description="Truncation strategy: 'end', 'start', 'middle'",
    )


class FileParseResponse(BaseModel):
    """Response for parsed file"""

    filename: str
    content: str
    mime_type: str
    size: int
    truncated: bool
    original_length: int | None = None
    title: str | None = None


# Allowed file types for parsing
ALLOWED_PARSE_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "text/html",
}

# Max file size for parsing (10MB)
MAX_PARSE_FILE_SIZE = 10 * 1024 * 1024


@router.post("/parse", response_model=Response[FileParseResponse])
async def parse_file(
    file: UploadFile = File(...),
    max_content_length: int = Query(
        default=100000,
        ge=1000,
        le=500000,
        description="Maximum content length in characters",
    ),
    truncate_strategy: str = Query(
        default="end",
        description="Truncation strategy: 'end', 'start', 'middle'",
    ),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Parse a file and extract text content using MarkItDown.

    Supported formats:
    - Documents: PDF, DOCX, DOC, PPTX, PPT
    - Spreadsheets: XLSX, XLS
    - Text: TXT, MD, CSV, JSON, HTML

    Returns parsed content in markdown format with optional truncation.
    """
    # Validate file is present
    if not file.filename:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_required",
        )

    # Check if file type is supported
    if not file_parser_service.is_supported(file.filename):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="unsupported_file_type",
            data={
                "filename": file.filename,
                "supported": list(file_parser_service.SUPPORTED_EXTENSIONS.keys()),
            },
        )

    # Read file content
    content = await file.read()

    # Validate file size
    if len(content) > MAX_PARSE_FILE_SIZE:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_too_large",
            data={"max_size": MAX_PARSE_FILE_SIZE, "actual_size": len(content)},
        )

    # Validate truncate strategy
    if truncate_strategy not in ("end", "start", "middle"):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="invalid_truncate_strategy",
            data={"allowed": ["end", "start", "middle"]},
        )

    # Parse file
    try:
        config = FileParseConfig(
            max_content_length=max_content_length,
            truncate_strategy=truncate_strategy,
        )
        parsed = await file_parser_service.parse_file(
            file_content=content,
            filename=file.filename,
            config=config,
        )
    except ValueError as e:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="file_parse_error",
            data={"error": str(e)},
        )
    except Exception as e:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="file_parse_error",
            data={"error": str(e)},
        )

    return success(
        data=FileParseResponse(
            filename=parsed.filename,
            content=parsed.content,
            mime_type=parsed.mime_type,
            size=parsed.size,
            truncated=parsed.truncated,
            original_length=parsed.original_length,
            title=parsed.title,
        ),
        msg_key="file_parsed",
    )


@router.post("/parse/batch", response_model=Response[list[FileParseResponse]])
async def parse_files_batch(
    files: list[UploadFile] = File(...),
    max_content_length: int = Query(
        default=100000,
        ge=1000,
        le=500000,
        description="Maximum content length per file",
    ),
    truncate_strategy: str = Query(
        default="end",
        description="Truncation strategy: 'end', 'start', 'middle'",
    ),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Parse multiple files in batch.

    Maximum 5 files per request.
    """
    if len(files) > 5:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="too_many_files",
            data={"max_files": 5, "actual": len(files)},
        )

    config = FileParseConfig(
        max_content_length=max_content_length,
        truncate_strategy=truncate_strategy,
    )

    results: list[FileParseResponse] = []
    errors: list[dict] = []

    for file in files:
        if not file.filename:
            continue

        if not file_parser_service.is_supported(file.filename):
            errors.append(
                {"filename": file.filename, "error": "Unsupported file type"}
            )
            continue

        content = await file.read()

        if len(content) > MAX_PARSE_FILE_SIZE:
            errors.append(
                {"filename": file.filename, "error": "File too large"}
            )
            continue

        try:
            parsed = await file_parser_service.parse_file(
                file_content=content,
                filename=file.filename,
                config=config,
            )
            results.append(
                FileParseResponse(
                    filename=parsed.filename,
                    content=parsed.content,
                    mime_type=parsed.mime_type,
                    size=parsed.size,
                    truncated=parsed.truncated,
                    original_length=parsed.original_length,
                    title=parsed.title,
                )
            )
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    if errors and not results:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="all_files_failed",
            data={"errors": errors},
        )

    return success(
        data=results,
        msg_key="files_parsed",
    )
