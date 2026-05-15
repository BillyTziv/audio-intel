from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"

    UPLOAD_DIR: str = "/data/uploads"
    OUTPUT_DIR: str = "/data/outputs"

    WHISPER_MODEL: str = "large-v3"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "el"
    WHISPER_MODEL_DIR: str = "/data/models"

    CHUNK_SECONDS: int = 900
    OVERLAP_SECONDS: int = 10

    DIARIZATION_ENABLED: bool = False
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    DIARIZATION_DEVICE: str = "cpu"
    HF_TOKEN: str = ""

    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "llama3.1:8b"
    OLLAMA_URL: str = "http://ollama:11434"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
