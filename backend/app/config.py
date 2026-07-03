from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://clawd@localhost/vsks_crm"
    SECRET_KEY: str = "vsks-jwt-secret-key-change-in-production"
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

settings = Settings()
