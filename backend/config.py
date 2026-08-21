"""Application configuration.

Every setting can be overridden with an environment variable, which is how
PythonAnywhere is configured.  Locally, drop a ``.env`` file next to this file
(copy ``.env.example``) and it is loaded automatically.
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    return (os.getenv(name, str(default)).strip().lower()
            in ("1", "true", "yes", "on"))


def _list(name, default=""):
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # --- Database -------------------------------------------------------
    # Local XAMPP defaults; on PythonAnywhere set the DB_* vars to the values
    # from the "Databases" tab (see DEPLOYMENT.md).
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "spotify_clone")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        "?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # PythonAnywhere kills idle MySQL connections after 5 minutes, so recycle
    # well before that and always ping before handing a connection out.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # --- Cross-origin (the Vercel front-end talks to this API) ----------
    # Comma-separated list, e.g. "https://elite-minus.vercel.app,http://localhost:3000"
    CORS_ORIGINS = _list("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500")

    # Where to send a browser that lands on the API root.
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # --- Sessions (used by the server-rendered admin panel) -------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)

    # --- API tokens (used by the Vercel front-end) ----------------------
    # Signed, stateless tokens; no server-side session needed cross-origin.
    API_TOKEN_MAX_AGE = int(os.getenv("API_TOKEN_MAX_AGE", 60 * 60 * 24 * 14))

    # --- SMTP / e-mail (OTP codes) --------------------------------------
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)      # STARTTLS on port 587
    SMTP_USE_SSL = _bool("SMTP_USE_SSL", False)     # implicit SSL on port 465
    MAIL_FROM = os.getenv("MAIL_FROM", "") or SMTP_USER
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "EliteMinus")
    # With no SMTP_USER configured the mailer prints codes to the console
    # instead of sending them, so local development works offline.
    MAIL_SUPPRESS_SEND = _bool("MAIL_SUPPRESS_SEND", False) or not SMTP_USER

    # --- OTP policy ------------------------------------------------------
    OTP_LENGTH = int(os.getenv("OTP_LENGTH", 6))
    OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", 10))
    OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", 5))
    OTP_RESEND_SECONDS = int(os.getenv("OTP_RESEND_SECONDS", 60))

    # When true, a freshly verified account stays "pending" until an admin
    # approves it in the staff panel.  When false it goes straight to "active".
    REQUIRE_ADMIN_APPROVAL = _bool("REQUIRE_ADMIN_APPROVAL", False)

    # --- "Forgot password? Contact the developer" ------------------------
    DEVELOPER_NAME = os.getenv("DEVELOPER_NAME", "EliteMinus Developer")
    DEVELOPER_EMAIL = os.getenv("DEVELOPER_EMAIL", "") or SMTP_USER
    DEVELOPER_PHONE = os.getenv("DEVELOPER_PHONE", "")

    # --- Spotify ---------------------------------------------------------
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    # Must match a Redirect URI registered in your Spotify app dashboard.
    SPOTIFY_REDIRECT_URI = os.getenv(
        "SPOTIFY_REDIRECT_URI", "http://localhost:5000/api/spotify/callback")
    SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "PH")

    @property
    def spotify_enabled(self):
        return bool(self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET)
