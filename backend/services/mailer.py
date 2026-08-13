import asyncio
import hashlib
import html
import logging
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def smtp_is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def should_expose_password_reset_links() -> bool:
    return _env_flag("EXPOSE_PASSWORD_RESET_LINKS", default=False)


def _brand_name() -> str:
    return os.getenv("SMTP_FROM_NAME", "UR Academic Resource Hub").strip() or "UR Academic Resource Hub"


def _support_email() -> str:
    return os.getenv("SUPPORT_EMAIL", os.getenv("SMTP_FROM_EMAIL", "support@uracademicresourcehub.com")).strip()


def _brand_footer() -> str:
    return "\n".join(
        [
            "",
            _brand_name(),
            f"Support: {_support_email()}",
            "This is a transactional email regarding your account security or access.",
        ]
    )


def _recipient_log_id(email: str) -> str:
    """Return a non-reversible recipient reference for operational logs."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


def _email_logo_url() -> str:
    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    return f"{frontend_url}/favicon.svg" if frontend_url else ""


def _email_html_layout(*, title: str, greeting: str, paragraphs: list[str], action_label: str | None = None, action_url: str | None = None, notice: str | None = None) -> str:
    """Build the shared, mobile-friendly transactional email shell."""
    brand_name = html.escape(_brand_name())
    support_email = html.escape(_support_email())
    logo_url = _email_logo_url()
    logo_markup = (
        f'<img src="{html.escape(logo_url, quote=True)}" width="40" height="40" alt="{brand_name} logo" '
        'style="display:block;border:0;border-radius:8px;" />'
        if logo_url
        else ""
    )
    paragraphs_markup = "".join(f'<p style="margin:0 0 16px;color:#334155;font-size:16px;line-height:1.6;">{paragraph}</p>' for paragraph in paragraphs)
    action_markup = ""
    if action_label and action_url:
        action_markup = (
            '<p style="margin:24px 0;">'
            f'<a href="{html.escape(action_url, quote=True)}" style="display:inline-block;background:#f08a5d;color:#ffffff;'
            'padding:12px 20px;border-radius:8px;font-weight:700;text-decoration:none;">'
            f'{html.escape(action_label)}</a></p>'
        )
    notice_markup = (
        f'<p style="margin:20px 0 0;padding:12px 14px;background:#fff4e6;border-radius:8px;color:#7c2d12;font-size:14px;line-height:1.5;">{html.escape(notice)}</p>'
        if notice
        else ""
    )
    return f'''<!doctype html>
<html lang="en"><body style="margin:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 12px;background:#f8fafc;"><tr><td align="center">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
      <tr><td style="padding:24px 28px;background:#fff4e6;">{logo_markup}<div style="margin-top:10px;color:#0f172a;font-size:18px;font-weight:700;">{brand_name}</div></td></tr>
      <tr><td style="padding:32px 28px;"><h1 style="margin:0 0 18px;color:#0f172a;font-size:24px;line-height:1.3;">{html.escape(title)}</h1>
        <p style="margin:0 0 16px;color:#334155;font-size:16px;line-height:1.6;">{html.escape(greeting)}</p>{paragraphs_markup}{action_markup}{notice_markup}</td></tr>
      <tr><td style="padding:20px 28px;background:#f8fafc;color:#64748b;font-size:13px;line-height:1.5;">{brand_name}<br />Support: <a href="mailto:{support_email}" style="color:#c2410c;">{support_email}</a><br />This is a transactional email regarding your account security or access.</td></tr>
    </table>
  </td></tr></table>
</body></html>'''


def _attach_html(message: EmailMessage, html_body: str) -> EmailMessage:
    message.add_alternative(html_body, subtype="html")
    return message


def _build_password_reset_message(to_email: str, reset_url: str, expires_at: datetime) -> EmailMessage:
    from_email = os.getenv("SMTP_FROM_EMAIL", "no-reply@example.com")
    from_name = _brand_name()
    expires_label = expires_at.strftime("%Y-%m-%d %H:%M UTC")

    message = EmailMessage()
    message["Subject"] = "Reset your UR Academic Resource Hub password"
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "Hello,",
                "",
                "We received a request to reset your UR Academic Resource Hub password.",
                f"Use this link to choose a new password before {expires_label}:",
                reset_url,
                "",
                "If you did not request this, you can safely ignore this email.",
                "For your security, never share this link with anyone.",
                _brand_footer(),
            ]
        )
    )
    return _attach_html(
        message,
        _email_html_layout(
            title="Reset your password",
            greeting="Hello,",
            paragraphs=[
                "We received a request to reset your UR Academic Resource Hub password.",
                f"Use the secure button below before {html.escape(expires_label)}. If you did not request this, you can safely ignore this email.",
            ],
            action_label="Choose a new password",
            action_url=reset_url,
            notice="For your security, never share this link with anyone.",
        ),
    )


def _build_account_created_message(to_email: str, user_name: str, role: str, login_url: str) -> EmailMessage:
    from_email = os.getenv("SMTP_FROM_EMAIL", "no-reply@example.com")
    from_name = _brand_name()
    role_label = role or "user"
    display_name = user_name or "there"

    message = EmailMessage()
    message["Subject"] = "Welcome to UR Academic Resource Hub"
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email
    body_lines = [
        f"Hello {display_name},",
        "",
        "Your UR Academic Resource Hub account has been created successfully.",
        "",
        f"Email: {to_email}",
        f"Role: {role_label}",
        "",
        "You can now sign in and access the platform.",
        login_url,
        "",
        "If your selected role requires approval, your account has been created and is pending approval.",
        "Please wait for the next review step before assuming access to privileged features.",
        _brand_footer(),
    ]
    message.set_content("\n".join(body_lines))
    return _attach_html(
        message,
        _email_html_layout(
            title="Welcome to Paper Hub",
            greeting=f"Hello {display_name},",
            paragraphs=[
                "Your UR Academic Resource Hub account has been created successfully.",
                f"Your account role is {html.escape(role_label)}. You can now sign in and access the platform.",
                "If your selected role requires approval, your account remains a normal account until the management review is complete.",
            ],
            action_label="Sign in to Paper Hub",
            action_url=login_url,
        ),
    )


def _send_email_sync(message: EmailMessage) -> None:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    use_ssl = _env_flag("SMTP_USE_SSL", default=False)
    use_tls = _env_flag("SMTP_USE_TLS", default=not use_ssl)

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            if smtp_username:
                server.login(smtp_username, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if smtp_username:
            server.login(smtp_username, smtp_password)
        server.send_message(message)


async def send_password_reset_email(to_email: str, reset_url: str, expires_at: datetime) -> bool:
    if not smtp_is_configured():
        logger.warning("SMTP is not configured; password reset email was not sent (recipient=%s)", _recipient_log_id(to_email))
        return False

    message = _build_password_reset_message(to_email, reset_url, expires_at)
    try:
        await asyncio.to_thread(_send_email_sync, message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.warning("Password reset email delivery failed (recipient=%s, error=%s)", _recipient_log_id(to_email), type(exc).__name__)
        return False
    logger.info("Password reset email delivered (recipient=%s)", _recipient_log_id(to_email))
    return True


async def send_account_created_email(to_email: str, user_name: str, role: str, login_url: str) -> bool:
    if not smtp_is_configured():
        logger.warning("SMTP is not configured; account-created email was not sent (recipient=%s)", _recipient_log_id(to_email))
        return False

    message = _build_account_created_message(to_email, user_name, role, login_url)
    try:
        await asyncio.to_thread(_send_email_sync, message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.warning("Account-created email delivery failed (recipient=%s, error=%s)", _recipient_log_id(to_email), type(exc).__name__)
        return False
    logger.info("Account-created email delivered (recipient=%s)", _recipient_log_id(to_email))
    return True
