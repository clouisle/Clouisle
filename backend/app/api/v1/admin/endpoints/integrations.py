"""Unified integration administration with independent management domains."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from tortoise.exceptions import IntegrityError

from app.api import deps
from app.core.i18n import t
from app.integrations.credentials import encrypt_secret
from app.integrations.registry import IntegrationCapability, integration_registry
from app.models.integration import Integration
from app.models.user import User
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.integration import (
    IntegrationAdmin,
    IntegrationCreate,
    IntegrationTypeOut,
    IntegrationUpdate,
)
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services.sso import PKCE_PROVIDER_TYPES, SSOService

router = APIRouter()


def _can_manage(user: User, domain: str, operation: str) -> bool:
    return user.is_superuser or deps.user_has_global_permission(
        user, f"admin:integrations:{domain}:{operation}"
    )


def _capability_domain(capability: str) -> str:
    return "login" if capability == IntegrationCapability.USER_LOGIN else "settings"


def _domains(provider_type: str) -> tuple[str, ...]:
    """Permission domains that govern an integration instance.

    A builtin is configured through the settings domain; a login-capable type is
    governed by the login domain. Feishu carries both capabilities, so it answers
    to both — never to only one of them.
    """
    definition = integration_registry.get(provider_type)
    domains: list[str] = ["settings"] if definition.singleton else []
    for capability in definition.capabilities:
        domain = _capability_domain(capability)
        if domain not in domains:
            domains.append(domain)
    return tuple(domains) or ("login",)


def _can_read(user: User, provider_type: str) -> bool:
    return any(_can_manage(user, domain, "read") for domain in _domains(provider_type))


def _require(user: User, domain: str, operation: str) -> None:
    if not _can_manage(user, domain, operation):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="operation_not_permitted",
            status_code=403,
            permission=f"admin:integrations:{domain}:{operation}",
        )


def _require_read(user: User) -> None:
    if not any(_can_manage(user, domain, "read") for domain in ("login", "settings")):
        _require(user, "login", "read")


def _required_domains(integration: Integration, values: dict) -> set[str]:
    """Domains the caller must hold `update` on for the requested changes.

    Each field is charged to the domain that owns its meaning, so a settings
    administrator can never grant a new sign-in path and a login administrator
    can never rewrite builtin credentials. A capability list is charged for the
    entries it actually flips, so re-sending an unchanged capability neither
    grants nor requires the other domain.
    """
    definition = integration_registry.get(integration.provider_type)
    login_capable = IntegrationCapability.USER_LOGIN in definition.capabilities
    login_fields = "login" if login_capable else "settings"
    builtin_fields = "settings" if definition.singleton else "login"
    all_domains = _domains(integration.provider_type)
    domains: set[str] = set()
    for field in values:
        if field in {
            "name",
            "provider_type",
            "display_name",
            "icon_url",
            "button_text",
            "login_config",
            "attribute_mapping",
        }:
            domains.add(login_fields)
        elif field in {"config", "credentials"}:
            domains.add(builtin_fields)
        elif field == "enabled_capabilities":
            # Unsupported entries are dropped here; validation rejects them
            # before anything is written, so they cannot be used to shift the
            # permission check.
            supported = set(definition.capabilities)
            previous = set(integration.enabled_capabilities or [])
            if (
                integration.provider_type in {"wechat", "feishu"}
                and not integration.is_enabled
            ):
                previous.clear()
            changed = (previous & supported) ^ (
                set(values["enabled_capabilities"] or []) & supported
            )
            if changed:
                domains.update(_capability_domain(capability) for capability in changed)
            else:
                domains.update(all_domains)
        else:
            # `is_enabled` gates every capability the instance carries.
            domains.update(all_domains)
    return domains


def _admin_output(integration: Integration) -> IntegrationAdmin:
    definition = integration_registry.get(integration.provider_type)
    return IntegrationAdmin(
        id=integration.id,
        name=integration.name,
        provider_type=integration.provider_type,
        display_name=integration.display_name,
        icon_url=integration.icon_url,
        button_text=integration.button_text,
        is_enabled=integration.is_enabled,
        enabled_capabilities=integration.enabled_capabilities,
        supported_capabilities=list(definition.capabilities),
        config={
            key: value
            for key, value in integration.config.items()
            if key not in definition.secret_fields
        },
        credentials_configured=sorted(
            key for key, value in integration.credentials.items() if value
        ),
        login_config=integration.login_config,
        attribute_mapping=integration.attribute_mapping,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _validate_update(integration: Integration, values: dict) -> None:
    try:
        definition = integration_registry.get(
            values.get("provider_type", integration.provider_type)
        )
        previous = integration_registry.get(integration.provider_type)
        if previous.singleton and definition.provider_type != previous.provider_type:
            raise ValueError("Builtin integration type cannot be changed")
        if not previous.singleton and definition.singleton:
            raise ValueError("Login integrations cannot become builtin integrations")
        capabilities = values.get(
            "enabled_capabilities", integration.enabled_capabilities
        )
        if not set(capabilities).issubset(definition.capabilities):
            raise ValueError("Unsupported integration capability")
        if IntegrationCapability.USER_LOGIN not in definition.capabilities and (
            set(values) & {"login_config", "attribute_mapping", "button_text"}
        ):
            raise ValueError("Login configuration is not supported by this integration")
        credentials = {**integration.credentials, **values.get("credentials", {})}
        if not set(credentials).issubset(definition.secret_fields):
            raise ValueError("Unsupported integration credential field")
        config = values.get("config", integration.config)
        if set(config) & set(definition.secret_fields):
            raise ValueError("Credentials must use the credentials field")
    except (ValueError, TypeError) as exc:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="integration_invalid_configuration",
        ) from exc


async def _get_integration(integration_id: UUID) -> Integration:
    integration = await Integration.get_or_none(id=integration_id)
    if integration is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND, msg_key="integration_not_found"
        )
    return integration


@router.get("/types", response_model=Response[list[IntegrationTypeOut]])
async def list_integration_types(
    current_user: User = Depends(deps.get_current_active_user),
):
    _require_read(current_user)
    return success(
        data=[
            IntegrationTypeOut(
                provider_type=definition.provider_type,
                display_name=definition.display_name,
                supported_capabilities=list(definition.capabilities),
                singleton=definition.singleton,
            )
            for definition in integration_registry.all()
            if _can_read(current_user, definition.provider_type)
        ]
    )


@router.get("", response_model=Response[list[IntegrationAdmin]])
async def list_integrations(current_user: User = Depends(deps.get_current_active_user)):
    _require_read(current_user)
    integrations = await Integration.all()
    return success(
        data=[
            _admin_output(integration)
            for integration in integrations
            if _can_read(current_user, integration.provider_type)
        ]
    )


@router.post("", response_model=Response[IntegrationAdmin])
async def create_integration(
    request: Request,
    data: IntegrationCreate,
    current_user: User = Depends(
        deps.PermissionChecker("admin:integrations:login:update")
    ),
):
    _require(current_user, "login", "update")
    definition = integration_registry.get(data.provider_type)
    if (
        definition.singleton
        or IntegrationCapability.USER_LOGIN not in definition.capabilities
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="integration_invalid_configuration",
        )
    if await Integration.filter(name=data.name).first():
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
            msg_key="integration_name_exists",
        )
    values = data.model_dump(mode="json")
    values["credentials"] = {
        key: encrypt_secret(value) for key, value in data.credentials.items() if value
    }
    try:
        integration = await Integration.create(**values, created_by=current_user)
    except IntegrityError as exc:
        if await Integration.filter(name=data.name).exists():
            raise BusinessError(
                code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
                msg_key="integration_name_exists",
            ) from exc
        raise
    await AuditLogService.log(
        user=current_user,
        action="create_integration",
        resource_type="integration",
        resource_id=integration.id,
        resource_name=integration.name,
        operation="create",
        status="success",
        request=request,
        changes={"after": AuditLogService.snapshot(integration, "integration")},
    )
    return success(data=_admin_output(integration))


@router.delete("/connections/{connection_id}", response_model=Response[None])
async def admin_disconnect_sso(
    connection_id: UUID,
    request: Request,
    current_user: User = Depends(
        deps.PermissionChecker("admin:integrations:login:update")
    ),
):
    connection = await UserSSOConnection.get_or_none(id=connection_id).prefetch_related(
        "integration", "user"
    )
    if not connection:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND, msg_key="sso_connection_not_found"
        )
    target_user = connection.user
    if (
        not target_user.hashed_password
        and await UserSSOConnection.filter(user=target_user).count() <= 1
    ):
        raise BusinessError(
            code=ResponseCode.FORBIDDEN, msg_key="cannot_disconnect_only_auth_method"
        )
    integration_name = connection.integration.name
    audit_before = AuditLogService.snapshot(connection, "sso_connection")
    await connection.delete()
    await AuditLogService.log(
        user=current_user,
        action="disconnect_sso",
        resource_type="sso_connection",
        resource_id=connection_id,
        resource_name=integration_name,
        operation="delete",
        status="success",
        request=request,
        changes={"before": audit_before},
        metadata={
            "integration": integration_name,
            "target_user_id": str(target_user.id),
        },
    )
    return success()


@router.put("/{integration_id}", response_model=Response[IntegrationAdmin])
async def update_integration(
    integration_id: UUID,
    request: Request,
    data: IntegrationUpdate,
    current_user: User = Depends(deps.get_current_active_user),
):
    integration = await _get_integration(integration_id)
    values = data.model_dump(mode="json", exclude_unset=True)
    for domain in sorted(_required_domains(integration, values)):
        _require(current_user, domain, "update")
    if any(
        value is None and key not in {"icon_url", "button_text"}
        for key, value in values.items()
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="integration_invalid_configuration",
        )
    _validate_update(integration, values)
    if (
        integration.provider_type in {"wechat", "feishu"}
        and "enabled_capabilities" in values
    ):
        # Function switches are authoritative. Recover a legacy-disabled record
        # without adding a new master toggle or granting unrequested features.
        values["is_enabled"] = True
    if values.get("name") and values["name"] != integration.name:
        if await Integration.filter(name=values["name"]).first():
            raise BusinessError(
                code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
                msg_key="integration_name_exists",
            )
    audit_before = AuditLogService.snapshot(integration, "integration")
    secret_values = values.pop("credentials", {})
    credentials = dict(integration.credentials)
    for key, value in secret_values.items():
        if value:
            credentials[key] = encrypt_secret(value)
    integration.credentials = credentials
    if "login_config" in values:
        supplied_policy = data.login_config.model_dump(mode="json", exclude_unset=True)
        values["login_config"] = {**integration.login_config, **supplied_policy}
    for key, value in values.items():
        setattr(integration, key, value)
    try:
        await integration.save()
    except IntegrityError as exc:
        if (
            "name" in values
            and await Integration.filter(name=values["name"])
            .exclude(id=integration.id)
            .exists()
        ):
            raise BusinessError(
                code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
                msg_key="integration_name_exists",
            ) from exc
        raise
    await AuditLogService.log(
        user=current_user,
        action="update_integration",
        resource_type="integration",
        resource_id=integration.id,
        resource_name=integration.name,
        operation="update",
        status="success",
        request=request,
        changes=AuditLogService.build_changes(
            audit_before, AuditLogService.snapshot(integration, "integration")
        ),
    )
    return success(data=_admin_output(integration))


@router.delete("/{integration_id}", response_model=Response[None])
async def delete_integration(
    integration_id: UUID,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    integration = await _get_integration(integration_id)
    for domain in _domains(integration.provider_type):
        _require(current_user, domain, "update")
    if integration_registry.get(integration.provider_type).singleton:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="integration_builtin_cannot_delete",
        )
    audit_before = AuditLogService.snapshot(integration, "integration")
    await integration.delete()
    await AuditLogService.log(
        user=current_user,
        action="delete_integration",
        resource_type="integration",
        resource_id=integration_id,
        resource_name=integration.name,
        operation="delete",
        status="success",
        request=request,
        changes={"before": audit_before},
    )
    return success()


@router.post("/{integration_id}/test", response_model=Response[dict])
async def test_integration_connection(
    integration_id: UUID,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    integration = await _get_integration(integration_id)
    if (
        IntegrationCapability.USER_LOGIN
        not in integration_registry.get(integration.provider_type).capabilities
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="integration_invalid_configuration",
        )
    _require(current_user, "login", "update")
    try:
        instance = SSOService.get_provider_instance(integration)
        result = await instance.get_authorization_url(
            state="test_state", redirect_uri="http://localhost/callback"
        )
        if integration.provider_type in PKCE_PROVIDER_TYPES and (
            not isinstance(result, tuple) or len(result) != 3
        ):
            raise ValueError("Invalid authorization response")
        return success(
            data={"status": "success", "message": t("integration_config_valid")}
        )
    except Exception:
        await AuditLogService.log(
            user=current_user,
            action="test_integration_failed",
            resource_type="integration",
            resource_id=integration.id,
            resource_name=integration.name,
            operation="read",
            status="failed",
            request=request,
            error_message="integration_config_error_generic",
        )
        return success(
            data={"status": "error", "message": t("integration_config_error_generic")}
        )
