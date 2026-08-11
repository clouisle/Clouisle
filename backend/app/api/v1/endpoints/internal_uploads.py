"""Internal file endpoints for the upload gateway.

The Celery worker (``UPLOAD_STORAGE_MODE=remote``) has no local uploads
volume; every file operation it needs (read document bytes, save/delete
extracted media assets, delete files) is an explicit HTTP call to these
endpoints. The ``api`` process is the sole owner of the uploads directory.

Security:
- Every handler requires ``Authorization: Bearer {INTERNAL_API_TOKEN}``
  (constant-time compare).
- When ``INTERNAL_API_TOKEN`` is unset the router fails closed with 404 so the
  endpoints behave as if they do not exist.
- The router is mounted at ``/internal`` and must never be exposed publicly
  (Ingress routes only ``/api`` and ``/``); the worker reaches it via the api
  ClusterIP service directly.
"""

import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.api.v1.endpoints.upload import UPLOAD_ROOT
from app.core.config import settings
from app.services.document_processor import document_processor
from app.services.upload_storage import get_upload_storage_backend

router = APIRouter()


def _token_matches(token: str, authorization: str | None) -> bool:
    if not authorization:
        return False
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        return False
    return hmac.compare_digest(credentials, token)


async def require_internal_token(
    authorization: str | None = Header(default=None),
) -> None:
    token = settings.get_internal_api_token()
    if not token:
        # Fail closed: unconfigured gateway looks like it does not exist.
        raise HTTPException(status_code=404, detail="Not Found")
    if not _token_matches(token, authorization):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/uploads/read")
async def read_upload(
    key: str = Query(...),
    _: None = Depends(require_internal_token),
) -> Response:
    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    if not await storage.exists(key):
        raise HTTPException(status_code=404, detail="Not Found")
    return await storage.response(key)


@router.put("/uploads/save")
async def save_upload(
    request: Request,
    key: str = Query(...),
    _: None = Depends(require_internal_token),
) -> dict[str, str]:
    content = await request.body()
    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    storage_path = await storage.save(key, content)
    return {"storage_path": storage_path}


@router.head("/uploads/exists")
async def exists_upload(
    key: str = Query(...),
    _: None = Depends(require_internal_token),
) -> Response:
    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    if not await storage.exists(key):
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=200)


@router.delete("/uploads/delete")
async def delete_upload(
    key: str = Query(...),
    _: None = Depends(require_internal_token),
) -> Response:
    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    await storage.delete(key)
    return Response(status_code=204)


@router.put("/uploads/media/{kb_id}/{doc_id}")
async def save_media_asset(
    request: Request,
    kb_id: UUID,
    doc_id: UUID,
    _: None = Depends(require_internal_token),
) -> dict[str, object]:
    content = await request.body()
    content_type = request.headers.get("Content-Type", "application/octet-stream")
    return await document_processor._save_media_asset(
        kb_id=kb_id,
        document_id=doc_id,
        content_type=content_type,
        content=content,
    )


@router.delete("/uploads/media/{kb_id}/{doc_id}")
async def delete_media_assets(
    kb_id: UUID,
    doc_id: UUID,
    _: None = Depends(require_internal_token),
) -> Response:
    await document_processor.delete_media_assets(kb_id, doc_id)
    return Response(status_code=204)
