import sys

from pydantic import ValidationError
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://clawd@localhost/vsks_crm"
    # No hardcoded default: a leaked/guessable SECRET_KEY lets anyone forge JWTs.
    # Must be provided via env (.env locally, ${SECRET_KEY:?} in docker-compose.yml).
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    SUBSIDY_LIMIT: float = 26128070.0
    # Email (SMTP) — if SMTP_USER is empty, links are logged to console (dev mode)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@vsks.ru"
    BASE_URL: str = "https://gaaala.duckdns.org"

try:
    settings = Settings()
except ValidationError as exc:
    if "SECRET_KEY" in str(exc):
        sys.exit(
            "SECRET_KEY не задан. Укажи переменную окружения SECRET_KEY "
            "(см. .env.example) перед запуском backend — "
            "например: SECRET_KEY=$(python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
        )
    raise
