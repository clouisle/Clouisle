from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlsplit

MODEL_ENDPOINT_ALLOWLIST_SETTING = "model_endpoint_allowlist"
MODEL_ENDPOINT_ALLOWLIST_MAX_ENTRIES = 200

DEFAULT_MODEL_ENDPOINT_ALLOWLIST = [
    "https://api.openai.com",
    "https://api.anthropic.com",
    "https://generativelanguage.googleapis.com",
    "https://api.deepseek.com",
    "https://api.moonshot.cn",
    "https://open.bigmodel.cn",
    "https://dashscope.aliyuncs.com",
    "https://api.baichuan-ai.com",
    "https://api.minimax.chat",
    "https://ark.cn-beijing.volces.com",
    "https://openspeech.bytedance.com",
    "https://api.siliconflow.cn",
    "https://api.x.ai",
    "http://localhost:11434",
    "https://api.dev.runwayml.com",
    "https://api.pika.art",
    "https://api.lumalabs.ai",
    "https://api.klingai.com",
    "https://api.stability.ai",
]


class ModelEndpointPolicyError(ValueError):
    def __init__(self, msg_key: str, *, origin: str | None = None) -> None:
        self.msg_key = msg_key
        self.origin = origin
        super().__init__(origin or msg_key)


def normalize_model_endpoint_origin(value: str) -> str:
    if not isinstance(value, str):
        raise ModelEndpointPolicyError("model_endpoint_base_url_invalid")

    raw_value = value.strip()
    if not raw_value:
        raise ModelEndpointPolicyError("model_endpoint_base_url_invalid")

    parsed = urlsplit(raw_value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ModelEndpointPolicyError("model_endpoint_base_url_invalid")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ModelEndpointPolicyError("model_endpoint_base_url_invalid") from exc

    host = parsed.hostname.rstrip(".")
    if not host or any(character.isspace() for character in host):
        raise ModelEndpointPolicyError("model_endpoint_base_url_invalid")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ModelEndpointPolicyError("model_endpoint_base_url_invalid") from exc
    else:
        host = ip.compressed
        if ip.version == 6:
            host = f"[{host}]"

    scheme = parsed.scheme.lower()
    default_port = 80 if scheme == "http" else 443
    port_suffix = f":{port}" if port is not None and port != default_port else ""
    return f"{scheme}://{host}{port_suffix}"


def normalize_model_endpoint_allowlist(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > MODEL_ENDPOINT_ALLOWLIST_MAX_ENTRIES:
        raise ModelEndpointPolicyError("model_endpoint_allowlist_invalid")

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, str):
            raise ModelEndpointPolicyError("model_endpoint_allowlist_invalid")
        try:
            origin = normalize_model_endpoint_origin(entry)
        except ModelEndpointPolicyError as exc:
            raise ModelEndpointPolicyError("model_endpoint_allowlist_invalid") from exc
        if origin not in seen:
            seen.add(origin)
            normalized.append(origin)
    return normalized


def model_endpoint_origin_is_allowed(
    base_url: str,
    allowlist: Iterable[str],
) -> str:
    origin = normalize_model_endpoint_origin(base_url)
    normalized_allowlist = normalize_model_endpoint_allowlist(list(allowlist))
    # Return the administrator-approved canonical value to outbound clients.
    for allowed_origin in normalized_allowlist:
        if origin == allowed_origin:
            return allowed_origin
    raise ModelEndpointPolicyError(
        "model_endpoint_not_allowlisted",
        origin=origin,
    )


async def get_model_endpoint_allowlist() -> list[str]:
    from app.models.site_setting import SiteSetting

    value = await SiteSetting.get_value(
        MODEL_ENDPOINT_ALLOWLIST_SETTING,
        DEFAULT_MODEL_ENDPOINT_ALLOWLIST,
    )
    try:
        return normalize_model_endpoint_allowlist(value)
    except ModelEndpointPolicyError:
        return []


async def ensure_model_endpoint_allowed(base_url: str | None) -> str | None:
    if base_url is None or not base_url.strip():
        return None
    allowlist = await get_model_endpoint_allowlist()
    return model_endpoint_origin_is_allowed(base_url, allowlist)
