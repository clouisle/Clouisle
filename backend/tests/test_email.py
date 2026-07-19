from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import email


@pytest.mark.asyncio
async def test_get_smtp_config_reads_site_settings():
    values = {
        "smtp_enabled": True,
        "smtp_host": "smtp.example.test",
        "smtp_port": 465,
        "smtp_encryption": "ssl",
        "smtp_username": "sender",
        "smtp_password": "secret",
        "email_from_name": "Clouisle Test",
        "email_from_address": "sender@example.test",
    }
    with patch(
        "app.core.email.SiteSetting.get_value",
        new=AsyncMock(side_effect=lambda key, default: values.get(key, default)),
    ):
        assert await email.get_smtp_config() == {
            "enabled": True,
            "host": "smtp.example.test",
            "port": 465,
            "encryption": "ssl",
            "username": "sender",
            "password": "secret",
            "from_name": "Clouisle Test",
            "from_address": "sender@example.test",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"enabled": False},
        {"enabled": True, "host": "", "from_address": "sender@example.test"},
        {"enabled": True, "host": "smtp.example.test", "from_address": ""},
    ],
)
async def test_send_email_skips_disabled_or_incomplete_smtp(config):
    with patch("app.core.email.get_smtp_config", new=AsyncMock(return_value=config)):
        assert (
            await email.send_email("recipient@example.test", "Subject", "Body") is False
        )


@pytest.mark.asyncio
async def test_send_email_builds_ssl_multipart_message():
    config = {
        "enabled": True,
        "host": "smtp.example.test",
        "port": 465,
        "encryption": "ssl",
        "username": "sender",
        "password": "secret",
        "from_name": "Clouisle Test",
        "from_address": "sender@example.test",
    }
    sender = AsyncMock()
    with (
        patch("app.core.email.get_smtp_config", new=AsyncMock(return_value=config)),
        patch("app.core.email.aiosmtplib.send", new=sender),
    ):
        assert await email.send_email(
            "recipient@example.test", "Subject", "Plain body", "<p>HTML body</p>"
        )

    message = sender.await_args.args[0]
    assert message["Subject"] == "Subject"
    assert message["From"] == "Clouisle Test <sender@example.test>"
    assert message["To"] == "recipient@example.test"
    assert [part.get_content_type() for part in message.get_payload()] == [
        "text/plain",
        "text/html",
    ]
    assert sender.await_args.kwargs == {
        "hostname": "smtp.example.test",
        "port": 465,
        "username": "sender",
        "password": "secret",
        "use_tls": True,
        "start_tls": False,
    }


@pytest.mark.asyncio
async def test_send_email_returns_false_when_smtp_client_fails():
    config = {
        "enabled": True,
        "host": "smtp.example.test",
        "port": 587,
        "encryption": "tls",
        "username": "",
        "password": "",
        "from_name": "Clouisle",
        "from_address": "sender@example.test",
    }
    with (
        patch("app.core.email.get_smtp_config", new=AsyncMock(return_value=config)),
        patch(
            "app.core.email.aiosmtplib.send",
            new=AsyncMock(side_effect=OSError("offline")),
        ),
    ):
        assert (
            await email.send_email("recipient@example.test", "Subject", "Body") is False
        )


@pytest.mark.asyncio
async def test_verification_and_rate_limit_helpers_use_redis_keys():
    redis = MagicMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(
        side_effect=["123456:token", "user@example.test:register", "5"]
    )
    redis.delete = AsyncMock()
    redis.ttl = AsyncMock(side_effect=[30, -1])
    redis.incrby = AsyncMock(return_value=2)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()

    with (
        patch("app.core.email.get_redis", new=AsyncMock(return_value=redis)),
        patch("app.core.email.secrets.randbelow", return_value=1),
        patch("app.core.email.secrets.token_urlsafe", return_value="token"),
    ):
        assert await email.generate_verification_code("user@example.test") == (
            "111111",
            "token",
        )
        assert await email.verify_code("user@example.test", "123456")
        assert await email.verify_token("token") == ("user@example.test", "register")
        assert await email.check_email_cooldown("user@example.test") == (False, 30)
        assert await email.check_email_cooldown("user@example.test") == (True, 0)
        assert await email.check_bulk_email_rate("admin", max_per_hour=5) == (
            False,
            5,
            0,
        )
        await email.increment_bulk_email_count("admin", 2)
        await email.increment_recipient_email_count("user@example.test")

    redis.setex.assert_any_await(
        "verify:code:user@example.test:register", 600, "111111:token"
    )
    redis.delete.assert_any_await("verify:token:token")
    redis.expire.assert_any_await("email:rate:recipient:user@example.test", 86400)


@pytest.mark.asyncio
async def test_filters_recipients_by_rate_limit():
    with patch(
        "app.core.email.check_recipient_email_rate",
        new=AsyncMock(side_effect=[(True, 0), (False, 5)]),
    ):
        assert await email.filter_rate_limited_recipients(
            ["allowed@example.test", "limited@example.test"]
        ) == (
            ["allowed@example.test"],
            ["limited@example.test"],
        )
