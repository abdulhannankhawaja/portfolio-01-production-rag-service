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
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    max_upload_mb: int = 25
    max_question_chars: int = 2000
    top_k: int = 5
    min_retrieval_score: float | None = Field(default=None, ge=-1, le=1)
    chunk_size: int = 500
    chunk_overlap: int = 100
    pinecone_api_key: str | None = None
    pinecone_index: str = "rag-vectors"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    neon_database_url: str | None = None


settings = Settings()
