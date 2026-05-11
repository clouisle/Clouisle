"""
邮件模板加载与渲染模块
"""

import os
from functools import lru_cache

from app.core.i18n import t

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


@lru_cache(maxsize=16)
def load_template(filename: str) -> str:
    """从 templates 目录读取模板文件"""
    path = os.path.join(_TEMPLATES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_verification_email(
    site_name: str,
    code: str,
    verify_url: str | None,
    *,
    locale: str,
) -> tuple[str, str]:
    """
    渲染注册验证邮件

    Returns:
        Tuple[str, str]: (纯文本内容, HTML 内容)
    """
    if verify_url:
        text_section = t(
            "email_verify_link_text",
            lang=locale,
            verify_url=verify_url,
        )
        html_section = (
            '    <p style="text-align: center; margin: 20px 0;">\n'
            f'        <a href="{verify_url}" style="display: inline-block; background: #0066ff; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px;">{t("email_verify_button", lang=locale)}</a>\n'
            "    </p>\n"
            f'    <p style="color: #888; font-size: 13px; text-align: center;">{t("email_or_enter_code", lang=locale)}</p>\n'
            '    <div style="background: #f5f5f5; padding: 16px; text-align: center; margin: 12px 0; border-radius: 8px;">\n'
            f'        <span style="font-size: 28px; font-weight: bold; letter-spacing: 8px; color: #333;">{code}</span>\n'
            "    </div>"
        )
    else:
        text_section = ""
        html_section = (
            '    <div style="background: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">\n'
            f'        <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #333;">{code}</span>\n'
            "    </div>"
        )

    text_tpl = load_template("verify_email.txt")
    html_tpl = load_template("verify_email.html")

    body_text = text_tpl.format(
        site_name=site_name,
        code=code,
        verify_section=text_section,
        email_verification_heading=t("email_verification_heading", lang=locale),
        email_greeting=t("email_greeting", lang=locale),
        email_verification_intro=t(
            "email_verification_intro",
            lang=locale,
            site_name=site_name,
        ),
        email_code_validity=t("email_code_validity", lang=locale),
        email_verification_ignore_notice=t(
            "email_verification_ignore_notice",
            lang=locale,
        ),
    )
    body_html = html_tpl.format(
        site_name=site_name,
        code=code,
        verify_section=html_section,
        email_verification_heading=t("email_verification_heading", lang=locale),
        email_greeting=t("email_greeting", lang=locale),
        email_verification_intro=t(
            "email_verification_intro",
            lang=locale,
            site_name=site_name,
        ),
        email_code_validity=t("email_code_validity", lang=locale),
        email_verification_ignore_notice=t(
            "email_verification_ignore_notice",
            lang=locale,
        ),
    )
    return body_text, body_html


def render_reset_password_email(
    site_name: str,
    code: str,
    verify_url: str | None,
    *,
    locale: str,
) -> tuple[str, str]:
    """
    渲染密码重置邮件

    Returns:
        Tuple[str, str]: (纯文本内容, HTML 内容)
    """
    if verify_url:
        text_section = t(
            "email_reset_link_text",
            lang=locale,
            verify_url=verify_url,
        )
        html_section = (
            '    <p style="text-align: center; margin: 20px 0;">\n'
            f'        <a href="{verify_url}" style="display: inline-block; background: #0066ff; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px;">{t("email_reset_button", lang=locale)}</a>\n'
            "    </p>\n"
            f'    <p style="color: #888; font-size: 13px; text-align: center;">{t("email_or_enter_code", lang=locale)}</p>\n'
            '    <div style="background: #f5f5f5; padding: 16px; text-align: center; margin: 12px 0; border-radius: 8px;">\n'
            f'        <span style="font-size: 28px; font-weight: bold; letter-spacing: 8px; color: #333;">{code}</span>\n'
            "    </div>"
        )
    else:
        text_section = ""
        html_section = (
            '    <div style="background: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">\n'
            f'        <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #333;">{code}</span>\n'
            "    </div>"
        )

    text_tpl = load_template("reset_password.txt")
    html_tpl = load_template("reset_password.html")

    body_text = text_tpl.format(
        site_name=site_name,
        code=code,
        verify_section=text_section,
        email_reset_password_heading=t("email_reset_password_heading", lang=locale),
        email_greeting=t("email_greeting", lang=locale),
        email_reset_password_intro=t(
            "email_reset_password_intro",
            lang=locale,
            site_name=site_name,
        ),
        email_code_validity=t("email_code_validity", lang=locale),
        email_reset_password_ignore_notice=t(
            "email_reset_password_ignore_notice",
            lang=locale,
        ),
    )
    body_html = html_tpl.format(
        site_name=site_name,
        code=code,
        verify_section=html_section,
        email_reset_password_heading=t("email_reset_password_heading", lang=locale),
        email_greeting=t("email_greeting", lang=locale),
        email_reset_password_intro=t(
            "email_reset_password_intro",
            lang=locale,
            site_name=site_name,
        ),
        email_code_validity=t("email_code_validity", lang=locale),
        email_reset_password_ignore_notice=t(
            "email_reset_password_ignore_notice",
            lang=locale,
        ),
    )
    return body_text, body_html
