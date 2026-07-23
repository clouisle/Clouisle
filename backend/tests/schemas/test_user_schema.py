"""User schema ORM conversion coverage."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.user import User


def test_user_validation_converts_orm_attributes_and_defaults():
    created_at = datetime.now(UTC)
    orm_user = SimpleNamespace(
        id=uuid4(),
        username="reader",
        email="reader@example.com",
        is_active=True,
        is_superuser=False,
        email_verified=True,
        avatar_url=None,
        created_at=created_at,
        last_login=None,
        auth_source="password",
        external_id=None,
    )

    user = User.model_validate(orm_user)

    assert user.id == orm_user.id
    assert user.approval_status == "approved"
    assert user.locale == "en"
    assert user.force_password_change is False
    assert user.password_expiration_exempt is False
    assert user.roles == []
    assert user.sso_connections == []


def test_user_validation_accepts_plain_mappings():
    user = User.model_validate(
        {
            "id": uuid4(),
            "username": "operator",
            "email": "operator@example.com",
            "created_at": datetime.now(UTC),
            "auth_source": "sso",
        }
    )

    assert user.username == "operator"
    assert user.auth_source == "sso"
