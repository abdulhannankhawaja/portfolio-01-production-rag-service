from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Production RAG Service"
    data_dir: Path = Field(default=Path("data"))
    embedding_model: str = "intfloat/e5-small-v2"
    embedding_provider: str = "local"
    cohere_api_key: str | None = None
    cohere_embedding_model: str = "embed-multilingual-light-v3.0"
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    provider_max_retries: int = Field(default=2, ge=0, le=5)
    max_upload_mb: int = 25
    max_question_chars: int = 2000
    top_k: int = 5
    min_retrieval_score: float | None = Field(default=0.84, ge=-1, le=1)
    max_requests_per_minute: int = Field(default=60, gt=0)
    chunk_size: int = 500
    chunk_overlap: int = 100


settings = Settings()
