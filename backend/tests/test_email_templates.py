import pytest

from app.core import email as email_module
from app.core.email_templates import render_verification_email


def test_profile_email_template_uses_html_link_and_custom_copy() -> None:
    body_text, body_html = render_verification_email(
        "Clouisle",
        "123456",
        "https://example.com/verify?token=abc",
        locale="en",
        heading_key="email_profile_email_heading",
        intro_key="email_profile_email_intro",
        ignore_notice_key="email_profile_email_ignore_notice",
        button_key="email_profile_email_confirm_button",
    )

    assert "Please confirm the new email" in body_text
    assert "Confirm Your New Email" in body_html
    assert "Confirm New Email" in body_html
    assert "https://example.com/verify?token=abc" in body_text
    assert "https://example.com/verify?token=abc" in body_html
    assert "123456" in body_text
    assert "123456" in body_html


@pytest.mark.asyncio
async def test_send_profile_email_verification_uses_html_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, str | None] = {}

    async def fake_get_value(key: str, default: object = None) -> object:
        values = {
            "site_name": "Clouisle",
            "site_url": "https://example.com",
            "default_language": "en",
        }
        return values.get(key, default)

    async def fake_send_email(
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> bool:
        sent.update(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        return True

    monkeypatch.setattr(email_module.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(email_module, "send_email", fake_send_email)

    await email_module.send_verification_email(
        "new@example.com",
        "123456",
        "token-abc",
        "profile_email",
    )

    assert sent["to_email"] == "new@example.com"
    assert sent["subject"] == "【Clouisle】Confirm Your New Email"
    assert "123456" in sent["body_text"]
    assert "123456" in sent["body_html"]
    assert "Confirm Your New Email" in sent["body_html"]
