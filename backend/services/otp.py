"""One-time-password issuing and checking.

Policy (all tunable from the environment):

* 6-digit code, valid for 10 minutes
* only the bcrypt hash of the code is stored
* at most 5 wrong guesses per code, then it dies
* one new code per 60 seconds per e-mail address
"""
import secrets
from datetime import timedelta

from flask import current_app

from extensions import bcrypt, db
from models import EmailOTP, utcnow
from services import mailer


class OTPError(Exception):
    """Raised with a message that is safe to show the user."""

    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


def _generate_code():
    length = current_app.config["OTP_LENGTH"]
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _latest(email, purpose):
    return (EmailOTP.query
            .filter_by(email=email, purpose=purpose)
            .order_by(EmailOTP.created_at.desc(), EmailOTP.id.desc())
            .first())


def issue(email, purpose="register"):
    """Create a code, e-mail it, and return the ``EmailOTP`` row.

    Raises ``OTPError`` if the caller is asking too soon or the mail fails.
    """
    email = email.strip().lower()

    previous = _latest(email, purpose)
    if previous and previous.consumed_at is None:
        wait = previous.seconds_until_resend()
        if wait > 0:
            raise OTPError(
                f"Please wait {wait} more second{'s' if wait != 1 else ''} "
                "before requesting another code.", retry_after=wait)

    # Any older code for this address stops working the moment a new one is out.
    EmailOTP.query.filter_by(email=email, purpose=purpose,
                             consumed_at=None).delete(synchronize_session=False)

    code = _generate_code()
    ttl = current_app.config["OTP_TTL_MINUTES"]
    otp = EmailOTP(
        email=email,
        purpose=purpose,
        code_hash=bcrypt.generate_password_hash(code).decode("utf-8"),
        expires_at=utcnow() + timedelta(minutes=ttl),
    )
    db.session.add(otp)
    db.session.commit()

    if not mailer.send_otp(email, code, purpose=purpose, minutes=ttl):
        raise OTPError("We couldn't send the verification e-mail. "
                       "Check the address and try again in a moment.")
    return otp


def verify(email, code, purpose="register"):
    """Consume a code.  Raises ``OTPError`` on any failure."""
    email = (email or "").strip().lower()
    code = (code or "").strip()

    otp = _latest(email, purpose)
    if not otp or otp.consumed_at is not None:
        raise OTPError("No active code for this e-mail. Request a new one.")
    if otp.is_expired:
        raise OTPError("That code has expired. Request a new one.")
    if otp.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        raise OTPError("Too many incorrect attempts. Request a new code.")

    if not bcrypt.check_password_hash(otp.code_hash, code):
        otp.attempts += 1
        db.session.commit()
        left = current_app.config["OTP_MAX_ATTEMPTS"] - otp.attempts
        if left <= 0:
            raise OTPError("Too many incorrect attempts. Request a new code.")
        raise OTPError(f"That code is not correct. {left} attempt"
                       f"{'s' if left != 1 else ''} left.")

    otp.consumed_at = utcnow()
    db.session.commit()
    return otp


def purge_expired(older_than_hours=24):
    """Housekeeping — drop codes nobody can use any more."""
    cutoff = utcnow() - timedelta(hours=older_than_hours)
    deleted = (EmailOTP.query.filter(EmailOTP.created_at < cutoff)
               .delete(synchronize_session=False))
    db.session.commit()
    return deleted
