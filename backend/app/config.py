from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://clawd@localhost/vsks_crm"
    SECRET_KEY: str = "vsks-jwt-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    SUBSIDY_LIMIT: float = 26128070.0

settings = Settings()
