"""WeChat QR authorization lifecycle: login limits, redirects, binding commit."""

from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.integrations.credentials import encrypt_secret
from app.integrations.wechat import WeChatAPIError
from app.models.user import Team, User
from app.models.wechat_knowledge import WeChatKnowledgeBinding, WeChatKnowledgeLogin
from app.schemas.response import BusinessError
from app.services import wechat_connection as connection
from app.services.wechat_connection import utcnow


class FakeClient:
    """Stands in for the iLink transport: only QR endpoints are used here."""

    qrcode: dict = {}
    status: list[dict] = []
    error: Exception | None = None
    requests: list[tuple] = []

    def __init__(
        self,
        base_url: str = connection.WeChatClient.__init__.__defaults__[0],
        token: str = "",
    ):
        self.base_url = base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get_qrcode(self) -> dict:
        if self.error is not None:
            raise self.error
        return self.qrcode

    async def get_qrcode_status(
        self, qrcode: str, verify_code: str | None = None
    ) -> dict:
        FakeClient.requests.append((qrcode, verify_code, self.base_url))
        if isinstance(self.error, Exception):
            raise self.error
        return FakeClient.status.pop(0) if FakeClient.status else {"status": "wait"}


@pytest_asyncio.fixture(autouse=True)
def fake_transport(monkeypatch):
    FakeClient.qrcode = {}
    FakeClient.status = []
    FakeClient.error = None
    FakeClient.requests = []
    monkeypatch.setattr(connection, "WeChatClient", FakeClient)
    return FakeClient


@pytest_asyncio.fixture
async def db():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield context


async def make_user() -> User:
    return await User.create(
        id=uuid4(),
        username=f"user-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )


async def make_login(user: User, **overrides) -> WeChatKnowledgeLogin:
    values = {
        "user_id": user.id,
        "qrcode": encrypt_secret("qr-secret"),
        "qrcode_content": "qr-image",
        "expires_at": utcnow() + timedelta(minutes=5),
    }
    values.update(overrides)
    return await WeChatKnowledgeLogin.create(**values)


@pytest.mark.asyncio
async def test_start_login_purges_expired_and_enforces_the_active_limit(
    db, fake_transport
):
    user = await make_user()
    expired = await make_login(user, expires_at=utcnow() - timedelta(minutes=1))
    confirmed = await make_login(user, status="confirmed")
    for _ in range(3):
        await make_login(user)

    with pytest.raises(BusinessError) as limited:
        await connection.start_login(user)
    assert (limited.value.msg_key, limited.value.status_code) == (
        "wechat_login_limit",
        429,
    )
    assert not await WeChatKnowledgeLogin.filter(id=expired.id).exists()
    # Settled logins do not consume a slot.
    assert await WeChatKnowledgeLogin.filter(id=confirmed.id).exists()


@pytest.mark.asyncio
async def test_start_login_reports_transport_and_payload_failures(db, fake_transport):
    user = await make_user()
    fake_transport.error = WeChatAPIError("connection")
    with pytest.raises(BusinessError) as failed:
        await connection.start_login(user)
    assert (failed.value.msg_key, failed.value.status_code) == (
        "wechat_connection_failed",
        502,
    )

    fake_transport.error = None
    fake_transport.qrcode = {"qrcode": "", "qrcode_img_content": "image"}
    with pytest.raises(BusinessError) as incomplete:
        await connection.start_login(user)
    assert incomplete.value.msg_key == "wechat_connection_failed"

    fake_transport.qrcode = {"qrcode": "qr-1", "qrcode_img_content": "image"}
    login = await connection.start_login(user)
    assert login.qrcode_content == "image"
    assert login.status == "wait"
    assert login.expires_at > utcnow()
    from app.integrations.credentials import decrypt_secret

    assert decrypt_secret(login.qrcode) == "qr-1"


@pytest.mark.asyncio
async def test_poll_login_scopes_to_the_owner_and_expires_stale_authorizations(
    db, fake_transport
):
    owner = await make_user()
    other = await make_user()
    login = await make_login(owner)

    with pytest.raises(BusinessError) as missing:
        await connection.poll_login(login.id, other)
    assert (missing.value.msg_key, missing.value.status_code) == (
        "wechat_login_not_found",
        404,
    )

    stale = await make_login(owner, expires_at=utcnow() - timedelta(minutes=1))
    output = await connection.poll_login(stale.id, owner)
    assert output["status"] == "expired"
    assert (await WeChatKnowledgeLogin.get(id=stale.id)).status == "expired"
    # An expired ticket never calls the upstream status endpoint.
    assert fake_transport.requests == []


@pytest.mark.asyncio
async def test_poll_login_tracks_redirects_verify_codes_and_unknown_states(
    db, fake_transport
):
    user = await make_user()
    login = await make_login(user)

    fake_transport.status = [
        {"status": "scaned_but_redirect", "redirect_host": "ilinkai.weixin.qq.com"}
    ]
    output = await connection.poll_login(login.id, user)
    assert output["status"] == "scaned"
    assert (
        await WeChatKnowledgeLogin.get(id=login.id)
    ).base_url == connection.official_url("https://ilinkai.weixin.qq.com")

    fake_transport.status = [{"status": "need_verifycode"}]
    assert (await connection.poll_login(login.id, user, "1234"))[
        "status"
    ] == "need_verifycode"
    assert fake_transport.requests[-1][1] == "1234"

    fake_transport.status = [{"status": "weird"}]
    with pytest.raises(BusinessError) as unknown:
        await connection.poll_login(login.id, user)
    assert (unknown.value.msg_key, unknown.value.status_code) == (
        "wechat_connection_failed",
        502,
    )

    fake_transport.status = [{"status": "wait"}]
    fake_transport.error = WeChatAPIError("connection")
    with pytest.raises(BusinessError) as transport:
        await connection.poll_login(login.id, user)
    assert transport.value.msg_key == "wechat_connection_failed"

    fake_transport.status = [{"status": "binded_redirect"}]
    fake_transport.error = None
    with pytest.raises(BusinessError) as already:
        await connection.poll_login(login.id, user)
    assert already.value.msg_key == "wechat_already_connected"


@pytest.mark.asyncio
async def test_poll_login_creates_the_binding_only_with_complete_credentials(
    db, fake_transport, monkeypatch
):
    user = await make_user()
    login = await make_login(user)
    audited: list[dict] = []

    async def log(**kwargs):
        audited.append(kwargs)

    from app.services import audit_log

    monkeypatch.setattr(audit_log.AuditLogService, "log", log)

    fake_transport.status = [{"status": "confirmed", "bot_token": "token"}]
    with pytest.raises(BusinessError) as incomplete:
        await connection.poll_login(login.id, user)
    assert incomplete.value.msg_key == "wechat_connection_failed"

    fake_transport.status = [
        {
            "status": "confirmed",
            "bot_token": "bot-token",
            "ilink_user_id": "identity-1",
            "ilink_bot_id": "bot-1",
            "baseurl": "https://ilinkai.weixin.qq.com",
        }
    ]
    output = await connection.poll_login(login.id, user)

    assert output["status"] == "confirmed"
    assert output["binding"]["bot_id"] == "bot-1"
    stored = await WeChatKnowledgeBinding.get(wechat_user_id="identity-1")
    assert stored.user_id == user.id
    assert stored.base_url == connection.official_url("https://ilinkai.weixin.qq.com")
    assert [entry["action"] for entry in audited] == ["connect_wechat_binding"]
    refreshed = await WeChatKnowledgeLogin.get(id=login.id)
    assert (refreshed.status, refreshed.binding_id) == ("confirmed", stored.id)

    # Re-polling a confirmed ticket reuses its binding instead of minting one.
    fake_transport.status = []
    again = await connection.poll_login(login.id, user)
    assert again["binding"]["id"] == str(stored.id)
    assert await WeChatKnowledgeBinding.filter(wechat_user_id="identity-1").count() == 1


@pytest.mark.asyncio
async def test_poll_login_refuses_an_identity_owned_by_another_user(db, fake_transport):
    owner = await make_user()
    intruder = await make_user()
    team = await Team.create(id=uuid4(), name="Team")
    existing = await WeChatKnowledgeBinding.create(
        user=owner,
        wechat_user_id="shared-identity",
        bot_id="bot-owner",
        token=encrypt_secret("token"),
        base_url="https://ilinkai.weixin.qq.com",
        status="connected",
    )
    assert existing.user_id == owner.id

    login = await make_login(intruder)
    fake_transport.status = [
        {
            "status": "confirmed",
            "bot_token": "bot-token",
            "ilink_user_id": "shared-identity",
            "ilink_bot_id": "bot-intruder",
        }
    ]
    with pytest.raises(BusinessError) as conflict:
        await connection.poll_login(login.id, intruder)
    assert (conflict.value.msg_key, conflict.value.status_code) == (
        "wechat_identity_in_use",
        409,
    )
    assert (await WeChatKnowledgeLogin.get(id=login.id)).status != "confirmed"
    assert (await WeChatKnowledgeBinding.get(id=existing.id)).user_id == owner.id
    assert team.name == "Team"
