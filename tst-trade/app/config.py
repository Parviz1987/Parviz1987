"""TST Trade settings, read from the environment (.env next to the app)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROVIDERS = ("goldapi", "twelvedata", "demo")


@dataclass(frozen=True)
class Settings:
    app_password: str
    session_secret: str
    secret_is_fixed: bool          # False: a random secret, saved keys cannot be read after a restart
    price_provider: str            # goldapi | twelvedata | demo (from .env; the admin page can override it)
    poll_seconds: int
    cookie_secure: bool
    db_path: Path


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    secret = os.getenv("SESSION_SECRET", "").strip()
    provider = os.getenv("PRICE_PROVIDER", "goldapi").strip().lower()
    if provider not in PROVIDERS:
        provider = "goldapi"
    try:
        poll = max(5, int(os.getenv("PRICE_POLL_SECONDS", "15")))
    except ValueError:
        poll = 15
    db = Path(os.getenv("DB_PATH", "data/lab.sqlite3"))
    if not db.is_absolute():
        db = BASE_DIR / db
    return Settings(
        app_password=os.getenv("APP_PASSWORD", ""),
        session_secret=secret or secrets.token_hex(32),
        secret_is_fixed=bool(secret),
        price_provider=provider,
        poll_seconds=poll,
        cookie_secure=os.getenv("COOKIE_SECURE", "1").strip() not in ("0", "false", "no"),
        db_path=db,
    )
