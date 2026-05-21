from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    UPLOAD_DIR: str = "/data/uploads"
    OUTPUT_DIR: str = "/data/outputs"
    MAX_UPLOAD_MB: int = 2048

    WHISPER_LANGUAGE: str = "el"
    CHUNK_SECONDS: int = 900
    OVERLAP_SECONDS: int = 10

    LOG_LEVEL: str = "INFO"

    MS_CLIENT_ID: str = ""
    MS_CLIENT_SECRET: str = ""
    MS_TENANT_ID: str = "common"
    MS_REDIRECT_URI: str = "http://localhost:8080/api/teams/auth/callback"
    MS_POST_LOGIN_REDIRECT: str = "http://localhost:8080/teams"

    # Comma-separated list of allowed CORS origins (no trailing slash).
    # Empty = same-origin only (localhost dev behind nginx works without CORS).
    CORS_ALLOW_ORIGINS: str = ""

    ALLOWED_AUDIO_MIME: tuple[str, ...] = Field(
        default=(
            "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
            "audio/ogg", "audio/flac", "audio/x-flac", "audio/mp4",
            "audio/x-m4a", "audio/aac", "audio/webm", "video/mp4",
            "video/webm", "application/octet-stream",
        )
    )
    ALLOWED_AUDIO_EXT: tuple[str, ...] = Field(
        default=(".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".webm", ".mp4")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
