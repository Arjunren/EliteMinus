"""E-mail delivery over plain SMTP (``smtplib`` from the standard library).

Works with any provider.  For Gmail you need an **App Password** — a normal
account password is rejected.  See DEPLOYMENT.md.

If ``SMTP_USER`` is empty (or ``MAIL_SUPPRESS_SEND=true``) nothing is sent and
the message is printed to the console instead, so the sign-up flow can be tested
offline.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app

BRAND = "#facc15"


def _connection():
    cfg = current_app.config
    host, port = cfg["SMTP_HOST"], cfg["SMTP_PORT"]
    if cfg["SMTP_USE_SSL"]:
        return smtplib.SMTP_SSL(host, port, timeout=20,
                                context=ssl.create_default_context())
    server = smtplib.SMTP(host, port, timeout=20)
    if cfg["SMTP_USE_TLS"]:
        server.starttls(context=ssl.create_default_context())
    return server


def send(to, subject, html, text=None):
    """Send one message.  Returns ``True`` if it went out (or was suppressed).

    Never raises: a mail outage should surface as a friendly error, not a 500.
    """
    cfg = current_app.config

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["MAIL_FROM_NAME"], cfg["MAIL_FROM"] or "noreply@localhost"))
    msg["To"] = to
    msg.set_content(text or _strip_tags(html))
    msg.add_alternative(html, subtype="html")

    if cfg["MAIL_SUPPRESS_SEND"]:
        current_app.logger.warning(
            "[mail suppressed] to=%s subject=%s\n%s", to, subject,
            text or _strip_tags(html))
        return True

    try:
        with _connection() as server:
            if cfg["SMTP_USER"]:
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            server.send_message(msg)
        return True
    except Exception as exc:                      # noqa: BLE001 - report, don't crash
        current_app.logger.error("SMTP send failed to %s: %s", to, exc)
        return False


def _strip_tags(html):
    import re
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</(p|div|h1|h2|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------
def _shell(body):
    return f"""\
<div style="background:#0f0f0f;padding:32px 0;font-family:Segoe UI,Helvetica,Arial,sans-serif">
  <div style="max-width:520px;margin:0 auto;background:#181818;border-radius:14px;
              padding:32px;color:#e5e5e5">
    <p style="margin:0 0 24px;font-size:22px;font-weight:700;color:#fff">
      Elite<span style="color:{BRAND}">Minus-</span>
    </p>
    {body}
    <p style="margin:32px 0 0;padding-top:16px;border-top:1px solid #2a2a2a;
              font-size:12px;color:#8a8a8a">
      This is an automated message from EliteMinus. Please don't reply.
    </p>
  </div>
</div>"""


def send_otp(to, code, purpose="register", minutes=10):
    """E-mail a verification code."""
    heading = {
        "register": "Confirm your e-mail",
        "login": "Confirm it's you",
    }.get(purpose, "Your verification code")

    body = f"""\
    <h1 style="margin:0 0 12px;font-size:20px;color:#fff">{heading}</h1>
    <p style="margin:0 0 20px;font-size:14px;line-height:1.6">
      Enter this code to finish setting up your EliteMinus account.
    </p>
    <p style="margin:0 0 20px;background:#0f0f0f;border:1px solid #2a2a2a;
              border-radius:10px;padding:18px;text-align:center;
              font-size:34px;font-weight:700;letter-spacing:10px;color:{BRAND}">
      {code}
    </p>
    <p style="margin:0;font-size:13px;color:#a3a3a3">
      The code expires in {minutes} minutes. If you didn't request it you can
      safely ignore this e-mail — nobody can access your account without it.
    </p>"""
    return send(to, f"{code} is your EliteMinus verification code", _shell(body))


def send_welcome(to, name):
    body = f"""\
    <h1 style="margin:0 0 12px;font-size:20px;color:#fff">Welcome, {name}!</h1>
    <p style="margin:0 0 16px;font-size:14px;line-height:1.6">
      Your e-mail is verified and your EliteMinus account is ready. You can now
      build playlists, queue up tracks and listen from any device.
    </p>
    <p style="margin:0;font-size:13px;color:#a3a3a3">
      Forgot your password later on? Passwords can only be reset by the
      developer — just get in touch and we'll sort it out.
    </p>"""
    return send(to, "Welcome to EliteMinus", _shell(body))


def send_password_help_request(dev_email, requester_email, username, message, ip):
    """Forward a 'forgot password' request to the developer."""
    body = f"""\
    <h1 style="margin:0 0 12px;font-size:20px;color:#fff">Password reset request</h1>
    <table style="width:100%;font-size:14px;border-collapse:collapse">
      <tr><td style="padding:6px 0;color:#a3a3a3">Account</td>
          <td style="padding:6px 0;color:#fff">{username or "—"}</td></tr>
      <tr><td style="padding:6px 0;color:#a3a3a3">E-mail</td>
          <td style="padding:6px 0;color:#fff">{requester_email}</td></tr>
      <tr><td style="padding:6px 0;color:#a3a3a3">From IP</td>
          <td style="padding:6px 0;color:#fff">{ip or "—"}</td></tr>
    </table>
    <p style="margin:18px 0 6px;color:#a3a3a3;font-size:13px">Message</p>
    <p style="margin:0;background:#0f0f0f;border-radius:8px;padding:14px;
              font-size:14px;line-height:1.6;white-space:pre-wrap">{message or "(none)"}</p>
    <p style="margin:20px 0 0;font-size:13px;color:#a3a3a3">
      Reset it from the admin panel → Staff → Reset password.
    </p>"""
    return send(dev_email, f"[EliteMinus] Password help for {username or requester_email}",
                _shell(body))


def send_account_notice(to, name, subject, message):
    """Generic notice sent by an admin (approved / suspended / password reset)."""
    body = f"""\
    <h1 style="margin:0 0 12px;font-size:20px;color:#fff">Hi {name},</h1>
    <p style="margin:0;font-size:14px;line-height:1.6;white-space:pre-wrap">{message}</p>"""
    return send(to, subject, _shell(body))
