import hashlib
import html
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


BREVO_EMAIL_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT_SECONDS = 15.0


def brevo_is_configured() -> bool:
    return bool(os.getenv("BREVO_API_KEY") and os.getenv("SMTP_FROM_EMAIL"))


def _brand_name() -> str:
    return os.getenv("SMTP_FROM_NAME", "UR Academic Resource Hub").strip() or "UR Academic Resource Hub"


def _support_email() -> str:
    return os.getenv("SUPPORT_EMAIL", os.getenv("SMTP_FROM_EMAIL", "support@uracademicresourcehub.com")).strip()


def _public_website_url() -> str:
    return os.getenv("FRONTEND_URL", "https://paperhubur.vercel.app").rstrip("/")


def _email_logo_url() -> str:
    frontend_url = _public_website_url()
    return f"{frontend_url}/favicon.svg" if frontend_url else ""


def _brand_footer() -> str:
    brand = _brand_name()
    support = _support_email()
    website = _public_website_url()
    return "\n".join(
        [
            "--------------------------------------------------",
            f"{brand} — University of Rwanda Academic Platform",
            f"Website: {website}",
            f"Support: {support}",
            "",
            "This is an automated transactional email regarding your account activity or platform security.",
            "If you did not initiate this request or have security questions, please contact support immediately.",
            "© 2026 UR Academic Resource Hub · All rights reserved.",
        ]
    )


def _recipient_log_id(email: str) -> str:
    """Return a non-reversible recipient reference for operational logs."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


def _email_html_layout(
    *,
    title: str,
    greeting: str,
    paragraphs: list[str],
    badge_label: str | None = None,
    badge_type: str = "default",
    action_label: str | None = None,
    action_url: str | None = None,
    notice: str | None = None,
    notice_type: str = "warning",
    feature_blocks: list[dict] | None = None,
    details_table: list[dict] | None = None,
    raw_extra_html: str | None = None,
) -> str:
    """Build a world-class, responsive, brand-strict transactional HTML email."""
    brand_name = html.escape(_brand_name())
    support_email = html.escape(_support_email())
    website_url = html.escape(_public_website_url(), quote=True)
    logo_url = _email_logo_url()

    # Category badge styling in header
    badge_markup = ""
    if badge_label:
        badge_bg = "rgba(249, 115, 22, 0.15)"
        badge_color = "#f97316"
        badge_border = "rgba(249, 115, 22, 0.35)"
        if badge_type == "security":
            badge_bg = "rgba(239, 68, 68, 0.15)"
            badge_color = "#ef4444"
            badge_border = "rgba(239, 68, 68, 0.35)"
        elif badge_type == "success":
            badge_bg = "rgba(16, 185, 129, 0.15)"
            badge_color = "#10b981"
            badge_border = "rgba(16, 185, 129, 0.35)"
        elif badge_type == "system":
            badge_bg = "rgba(59, 130, 246, 0.15)"
            badge_color = "#3b82f6"
            badge_border = "rgba(59, 130, 246, 0.35)"

        badge_markup = (
            f'<span style="display:inline-block;padding:4px 10px;background:{badge_bg};color:{badge_color};'
            f'border:1px solid {badge_border};border-radius:9999px;font-size:11px;font-weight:700;'
            f'letter-spacing:0.06em;text-transform:uppercase;">{html.escape(badge_label)}</span>'
        )

    # Header logo markup
    logo_img_markup = (
        f'<img src="{html.escape(logo_url, quote=True)}" width="36" height="36" alt="{brand_name}" '
        'style="display:block;border:0;border-radius:8px;" />'
        if logo_url
        else '<span style="display:inline-block;width:36px;height:36px;line-height:36px;text-align:center;background:#f97316;color:#ffffff;border-radius:8px;font-weight:800;font-size:18px;">UR</span>'
    )

    # Paragraphs markup
    paragraphs_markup = "".join(
        f'<p style="margin:0 0 16px;color:#334155;font-size:15px;line-height:1.65;">{p}</p>' for p in paragraphs
    )

    # Feature blocks (e.g. Welcome onboard tiles / Inactivity highlights)
    features_markup = ""
    if feature_blocks:
        cards_html = []
        for block in feature_blocks:
            icon = block.get("icon", "✦")
            block_title = html.escape(block.get("title", ""))
            block_desc = html.escape(block.get("description", ""))
            cards_html.append(
                f'<div style="margin-bottom:12px;padding:14px 16px;background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;">'
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
                f'<td width="32" valign="top" style="font-size:20px;line-height:1.2;padding-right:12px;">{icon}</td>'
                f'<td valign="top"><div style="color:#9a3412;font-weight:700;font-size:14px;margin-bottom:3px;">{block_title}</div>'
                f'<div style="color:#7c2d12;font-size:13px;line-height:1.5;">{block_desc}</div></td>'
                f'</tr></table></div>'
            )
        features_markup = f'<div style="margin:20px 0 24px;">{"".join(cards_html)}</div>'

    # Key-value details table (e.g. for System Heartbeat & Security reports)
    details_markup = ""
    if details_table:
        rows_html = []
        for item in details_table:
            lbl = html.escape(str(item.get("label", "")))
            val = html.escape(str(item.get("value", "")))
            rows_html.append(
                f'<tr><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;">{lbl}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;font-weight:600;text-align:right;">{val}</td></tr>'
            )
        details_markup = (
            f'<div style="margin:20px 0 24px;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;background:#f8fafc;">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">'
            f'{"".join(rows_html)}</table></div>'
        )

    # Primary Action button
    action_markup = ""
    if action_label and action_url:
        action_markup = (
            '<table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0 28px;">'
            '<tr><td align="center" style="border-radius:10px;background:linear-gradient(135deg,#f97316 0%,#ea580c 100%);box-shadow:0 4px 12px rgba(234,88,12,0.25);">'
            f'<a href="{html.escape(action_url, quote=True)}" target="_blank" style="display:inline-block;padding:14px 28px;'
            'color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;letter-spacing:0.02em;border-radius:10px;">'
            f'{html.escape(action_label)} &rarr;</a></td></tr></table>'
        )

    # Notice box
    notice_markup = ""
    if notice:
        border_color = "#f97316"
        bg_color = "#fff7ed"
        text_color = "#7c2d12"
        if notice_type == "security":
            border_color = "#ef4444"
            bg_color = "#fef2f2"
            text_color = "#991b1b"
        elif notice_type == "info":
            border_color = "#3b82f6"
            bg_color = "#eff6ff"
            text_color = "#1e40af"
        elif notice_type == "success":
            border_color = "#10b981"
            bg_color = "#ecfdf5"
            text_color = "#065f46"

        notice_markup = (
            f'<div style="margin:22px 0 0;padding:14px 16px;background:{bg_color};border-left:4px solid {border_color};'
            f'border-radius:8px;color:{text_color};font-size:13px;line-height:1.55;">'
            f'{html.escape(notice)}</div>'
        )

    extra_content = raw_extra_html or ""

    return f"""<!doctype html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{html.escape(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f1f5f9;padding:32px 12px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background-color:#ffffff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;box-shadow:0 6px 20px rgba(15,23,42,0.06);">
          <!-- Elegant Top Brand Banner -->
          <tr>
            <td style="padding:24px 32px;background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);border-bottom:3px solid #f97316;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td width="44" valign="middle">{logo_img_markup}</td>
                  <td valign="middle" style="padding-left:14px;">
                    <div style="color:#ffffff;font-size:18px;font-weight:800;letter-spacing:-0.01em;line-height:1.2;">{brand_name}</div>
                    <div style="color:#94a3b8;font-size:12px;font-weight:500;margin-top:2px;">University of Rwanda · Academic Platform</div>
                  </td>
                  <td align="right" valign="middle">{badge_markup}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Email Content Body -->
          <tr>
            <td style="padding:36px 32px 28px;">
              <h1 style="margin:0 0 18px;color:#0f172a;font-size:23px;font-weight:800;line-height:1.3;letter-spacing:-0.02em;">{html.escape(title)}</h1>
              <p style="margin:0 0 16px;color:#0f172a;font-size:16px;font-weight:600;">{html.escape(greeting)}</p>
              {paragraphs_markup}
              {features_markup}
              {details_markup}
              {action_markup}
              {extra_content}
              {notice_markup}
            </td>
          </tr>

          <!-- High-End Multi-Tier Brand Footer -->
          <tr>
            <td style="padding:28px 32px;background-color:#f8fafc;border-top:1px solid #e2e8f0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="color:#64748b;font-size:13px;line-height:1.6;">
                    <strong style="color:#334155;font-weight:700;">{brand_name}</strong><br />
                    Empowering UR students and educators with verified past papers, curriculum books, and AI study tools.
                  </td>
                </tr>
                <tr>
                  <td style="padding:14px 0 12px;border-bottom:1px solid #e2e8f0;">
                    <a href="{website_url}" target="_blank" style="color:#ea580c;text-decoration:none;font-size:12px;font-weight:600;margin-right:14px;">Visit PaperHub</a>
                    <a href="{website_url}/resources" target="_blank" style="color:#ea580c;text-decoration:none;font-size:12px;font-weight:600;margin-right:14px;">Past Papers</a>
                    <a href="{website_url}/terms" target="_blank" style="color:#64748b;text-decoration:none;font-size:12px;font-weight:500;margin-right:14px;">Terms of Service</a>
                    <a href="{website_url}/privacy" target="_blank" style="color:#64748b;text-decoration:none;font-size:12px;font-weight:500;">Privacy Policy</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:14px;color:#94a3b8;font-size:11px;line-height:1.5;">
                    Support: <a href="mailto:{support_email}" style="color:#ea580c;text-decoration:underline;">{support_email}</a><br />
                    This is an automated operational notification regarding your account access and security.<br />
                    &copy; 2026 {brand_name}. All rights reserved.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_password_reset_message(to_email: str, reset_url: str, expires_at: datetime) -> dict:
    expires_label = expires_at.strftime("%Y-%m-%d %H:%M UTC")

    return {
        "subject": "Reset your PaperHub password",
        "text": "\n".join(
            [
                "Hello,",
                "",
                "We received a request to reset your UR Academic Resource Hub password.",
                f"Use this link to choose a new password before {expires_label}:",
                reset_url,
                "",
                "If you did not request this, you can safely ignore this email — your account remains secure.",
                "For your security, never share this link with anyone.",
                _brand_footer(),
            ]
        ),
        "html": _email_html_layout(
            title="Reset your password",
            greeting="Hello,",
            badge_label="Security",
            badge_type="security",
            paragraphs=[
                "We received a request to reset the password for your UR Academic Resource Hub account.",
                f"Click the secure button below to choose a new password. For your safety, this link is valid until <strong>{html.escape(expires_label)}</strong> (30 minutes).",
            ],
            action_label="Choose a new password",
            action_url=reset_url,
            notice="If you did not request a password reset, you can safely ignore this email. Your password will remain unchanged.",
            notice_type="security",
        ),
    }


def _build_account_created_message(to_email: str, user_name: str, role: str, login_url: str) -> dict:
    role_label = role or "user"
    display_name = user_name or "there"

    body_lines = [
        f"Hello {display_name},",
        "",
        "Welcome to UR Academic Resource Hub!",
        "Your account has been created successfully.",
        "",
        f"Email: {to_email}",
        f"Account Role: {role_label}",
        "",
        "You can now sign in and explore past exam papers, books, and study aids.",
        login_url,
        "",
        "Key features waiting for you:",
        "1. Verified Past Papers & CATs with solutions",
        "2. Curriculum-aligned Textbooks & Modules",
        "3. Interactive AI Study Assistant",
        "",
        "If your selected role requires administrative review, your account remains active as a standard account until verified.",
        _brand_footer(),
    ]
    return {
        "subject": "Welcome to PaperHub",
        "text": "\n".join(body_lines),
        "html": _email_html_layout(
            title="Welcome to Paper Hub!",
            greeting=f"Hello {display_name},",
            badge_label="Welcome",
            badge_type="success",
            paragraphs=[
                "Welcome to <strong>UR Academic Resource Hub</strong>! Your account has been created successfully.",
                f"You are registered with the role <strong>{html.escape(role_label)}</strong> ({html.escape(to_email)}). Get started exploring everything the platform offers for your courses and revision:",
            ],
            feature_blocks=[
                {
                    "icon": "📄",
                    "title": "Access Past Papers & CATs",
                    "description": "Download verified exams, tests, and answer keys across University of Rwanda colleges and schools.",
                },
                {
                    "icon": "📚",
                    "title": "Textbooks & Course Notes",
                    "description": "Browse recommended reference textbooks and modular reading materials.",
                },
                {
                    "icon": "🤖",
                    "title": "AI Study Companion",
                    "description": "Generate practice questions, quick summaries, and question-by-question explanations.",
                },
            ],
            action_label="Sign in to Paper Hub",
            action_url=login_url,
            notice="Tip: Complete your profile with your campus, college, and department to receive personalized resource recommendations.",
            notice_type="info",
        ),
    }


def _build_password_changed_message(to_email: str, user_name: str, changed_at: datetime) -> dict:
    timestamp_label = changed_at.strftime("%Y-%m-%d %H:%M UTC")
    display_name = user_name or "there"

    return {
        "subject": "Your PaperHub password was changed",
        "text": "\n".join(
            [
                f"Hello {display_name},",
                "",
                f"Your PaperHub password was successfully changed on {timestamp_label}.",
                "",
                "If you made this change, no further action is required.",
                "If you did NOT make this change, please contact support immediately or reset your password to secure your account.",
                _brand_footer(),
            ]
        ),
        "html": _email_html_layout(
            title="Password Changed Successfully",
            greeting=f"Hello {display_name},",
            badge_label="Security Alert",
            badge_type="security",
            paragraphs=[
                f"This is a confirmation that your PaperHub account password was successfully updated on <strong>{html.escape(timestamp_label)}</strong>.",
                "If you authorized this change, you can safely disregard this message.",
            ],
            action_label="Review Account Security",
            action_url=f"{_public_website_url()}/profile",
            notice="Security Warning: If you did not make this change, your account may be compromised. Please reset your password immediately and contact support.",
            notice_type="security",
        ),
    }


def _build_new_login_message(to_email: str, user_name: str, login_at: datetime) -> dict:
    timestamp_label = login_at.strftime("%Y-%m-%d %H:%M UTC")
    display_name = user_name or "there"

    return {
        "subject": "New sign-in to your PaperHub account",
        "text": "\n".join(
            [
                f"Hello {display_name},",
                "",
                f"A new sign-in to your PaperHub account was detected on {timestamp_label}.",
                "",
                "If this was you, no action is needed.",
                "If you do not recognize this sign-in, please change your password immediately and contact support.",
                _brand_footer(),
            ]
        ),
        "html": _email_html_layout(
            title="New Sign-in Detected",
            greeting=f"Hello {display_name},",
            badge_label="Sign-in Notice",
            badge_type="default",
            paragraphs=[
                f"A new sign-in to your UR Academic Resource Hub account was recorded on <strong>{html.escape(timestamp_label)}</strong>.",
                "If this was you, you can safely ignore this notification.",
            ],
            action_label="View Profile & Security",
            action_url=f"{_public_website_url()}/profile",
            notice="If you did not sign in recently, change your password immediately to protect your academic records and uploads.",
            notice_type="warning",
        ),
    }


def _build_inactive_user_message(to_email: str, user_name: str, login_url: str) -> dict:
    display_name = user_name or "there"

    return {
        "subject": "We miss you at PaperHub — Discover New Academic Resources",
        "text": "\n".join(
            [
                f"Hello {display_name},",
                "",
                "We noticed you haven't visited UR Academic Resource Hub in a little while.",
                "New past papers, lecture notes, and textbook resources have been added for your courses!",
                "",
                f"Sign back in here: {login_url}",
                "",
                "Explore what is new:",
                "- Fresh past exam papers and verified CAT solutions",
                "- Updated books and module summaries",
                "- AI-powered study and exam prep tools",
                _brand_footer(),
            ]
        ),
        "html": _email_html_layout(
            title="We Miss You on PaperHub!",
            greeting=f"Hello {display_name},",
            badge_label="What's New",
            badge_type="success",
            paragraphs=[
                "It's been a little while since your last visit to <strong>UR Academic Resource Hub</strong>.",
                "Your peers and lecturers have recently uploaded new academic materials, past exams, and solution guides to help you excel this semester:",
            ],
            feature_blocks=[
                {
                    "icon": "📈",
                    "title": "Fresh Past Exam Papers & CATs",
                    "description": "Discover recently shared examination papers from your college with step-by-step solutions.",
                },
                {
                    "icon": "📖",
                    "title": "Textbooks & Module Handouts",
                    "description": "Explore digital books, reference notes, and study guides curated for your modules.",
                },
                {
                    "icon": "💡",
                    "title": "AI Study Companion",
                    "description": "Review questions, generate practice quizzes, and get instant explanations on complex topics.",
                },
            ],
            action_label="Explore Latest Resources",
            action_url=login_url,
            notice="Keep your skills sharp and stay ahead in your studies. Jump back in anytime!",
            notice_type="info",
        ),
    }


def _build_system_heartbeat_message(to_email: str, admin_name: str, health_data: dict) -> dict:
    now_label = datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status = str(health_data.get("status", "healthy")).upper()
    duration_ms = health_data.get("duration_ms", 0)
    mode = health_data.get("mode", "Scheduled Check")
    total_attempts = health_data.get("total_attempts", 1)
    total_successes = health_data.get("total_successes", 1)
    next_scheduled = health_data.get("next_scheduled", "Pending")

    badge_type = "success" if status == "HEALTHY" else "security" if status in ("FAILED", "DEGRADED") else "system"

    details_table = [
        {"label": "System Status", "value": status},
        {"label": "Execution Mode", "value": mode},
        {"label": "Database Latency", "value": f"{duration_ms} ms"},
        {"label": "Total Checks Completed", "value": f"{total_successes} / {total_attempts}"},
        {"label": "Next Scheduled Check", "value": next_scheduled},
        {"label": "Report Timestamp", "value": now_label},
    ]

    return {
        "subject": f"[System Health] Heartbeat: {status} — UR Academic Resource Hub",
        "text": "\n".join(
            [
                f"Hello {admin_name or 'Administrator'},",
                "",
                f"Automated System Health Heartbeat Report: {status}",
                f"Execution Mode: {mode}",
                f"Database Latency: {duration_ms} ms",
                f"Success Rate: {total_successes}/{total_attempts}",
                f"Next Check: {next_scheduled}",
                f"Timestamp: {now_label}",
                "",
                f"View details: {_public_website_url()}/admin",
                _brand_footer(),
            ]
        ),
        "html": _email_html_layout(
            title="System Health & Database Heartbeat Report",
            greeting=f"Hello {admin_name or 'Administrator'},",
            badge_label=f"Health: {status}",
            badge_type=badge_type,
            paragraphs=[
                f"The automated database activity heartbeat has executed on <strong>{html.escape(now_label)}</strong>.",
                "Here is the latest health telemetry recorded in the system health registry:",
            ],
            details_table=details_table,
            action_label="Open Admin System Health",
            action_url=f"{_public_website_url()}/admin",
            notice="Note: You are receiving this heartbeat telemetry because admin email notifications are enabled in Site Settings.",
            notice_type="info" if status == "HEALTHY" else "security",
        ),
    }


def _build_account_invitation_message(to_email: str, inviter_name: str, invitation_url: str) -> dict:
    inviter = inviter_name or "A colleague"

    return {
        "subject": "You are invited to PaperHub",
        "text": "\n".join(
            [
                "Hello,",
                "",
                f"{inviter} has invited you to join UR Academic Resource Hub (PaperHub).",
                "",
                f"Use this link to accept the invitation and create your account: {invitation_url}",
                "",
                "Join thousands of University of Rwanda students and educators sharing past papers, lecture notes, and books.",
                _brand_footer(),
            ]
        ),
        "html": _email_html_layout(
            title="You're Invited to PaperHub!",
            greeting="Hello,",
            badge_label="Invitation",
            badge_type="success",
            paragraphs=[
                f"<strong>{html.escape(inviter)}</strong> has invited you to join the <strong>UR Academic Resource Hub</strong>.",
                "Join our growing community of University of Rwanda students and faculty to access verified past papers, textbooks, and interactive AI study tools.",
            ],
            feature_blocks=[
                {"icon": "📄", "title": "Past Examination Papers", "description": "Search papers and vetted solutions by campus, college, school, and course."},
                {"icon": "📚", "title": "Textbooks & Library", "description": "Read and download curriculum-aligned modular books."},
                {"icon": "🤖", "title": "AI Study Companion", "description": "Get instant exam prep explanations and summaries."},
            ],
            action_label="Accept Invitation & Sign Up",
            action_url=invitation_url,
            notice="This invitation link is unique to you. Never share it with unauthorized users.",
            notice_type="info",
        ),
    }


async def send_transactional_email(to_email: str, subject: str, text: str, html_body: str) -> bool:
    if not brevo_is_configured():
        logger.warning("Transactional email not sent (recipient=%s, reason=brevo_not_configured)", _recipient_log_id(to_email))
        return False
    payload = {
        "sender": {"name": _brand_name(), "email": os.getenv("SMTP_FROM_EMAIL", "")},
        "to": [{"email": to_email}],
        "replyTo": {"email": _support_email()},
        "subject": subject,
        "textContent": text,
        "htmlContent": html_body,
    }
    try:
        async with httpx.AsyncClient(timeout=BREVO_TIMEOUT_SECONDS) as client:
            response = await client.post(
                BREVO_EMAIL_ENDPOINT,
                headers={"api-key": os.getenv("BREVO_API_KEY", ""), "accept": "application/json"},
                json=payload,
            )
        if response.status_code < 200 or response.status_code >= 300:
            logger.warning("Brevo delivery failed (recipient=%s, status=%s)", _recipient_log_id(to_email), response.status_code)
            return False
        provider_response = response.json()
        if not isinstance(provider_response, dict) or not isinstance(provider_response.get("messageId"), str):
            logger.warning("Brevo delivery returned malformed response (recipient=%s)", _recipient_log_id(to_email))
            return False
    except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
        logger.warning("Brevo delivery failed (recipient=%s, error=%s)", _recipient_log_id(to_email), type(exc).__name__)
        return False
    return True


async def send_password_reset_email(to_email: str, reset_url: str, expires_at: datetime) -> bool:
    message = _build_password_reset_message(to_email, reset_url, expires_at)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])


async def send_account_created_email(to_email: str, user_name: str, role: str, login_url: str) -> bool:
    message = _build_account_created_message(to_email, user_name, role, login_url)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])


async def send_password_changed_email(to_email: str, user_name: str, changed_at: datetime) -> bool:
    message = _build_password_changed_message(to_email, user_name, changed_at)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])


async def send_new_login_email(to_email: str, user_name: str, login_at: datetime) -> bool:
    message = _build_new_login_message(to_email, user_name, login_at)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])


async def send_inactive_user_email(to_email: str, user_name: str, login_url: str) -> bool:
    message = _build_inactive_user_message(to_email, user_name, login_url)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])


async def send_system_heartbeat_email(to_email: str, admin_name: str, health_data: dict) -> bool:
    message = _build_system_heartbeat_message(to_email, admin_name, health_data)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])


async def send_account_invitation_email(to_email: str, inviter_name: str, invitation_url: str) -> bool:
    message = _build_account_invitation_message(to_email, inviter_name, invitation_url)
    return await send_transactional_email(to_email, message["subject"], message["text"], message["html"])
