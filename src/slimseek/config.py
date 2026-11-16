from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SLIMSEEK_", env_file=".env", extra="ignore"
    )

    provider: Literal["openai", "ollama"] = "openai"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen2.5:3b"
    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    port: int = 8000
    upload_max_mb: int = Field(default=20, gt=0, le=100)
    request_timeout_seconds: float = Field(default=120, gt=0)
    chunk_size: int = Field(default=900, ge=200)
    chunk_overlap: int = Field(default=150, ge=0)
    context_max_chars: int = Field(default=12000, ge=1000)

    @model_validator(mode="after")
    def validate_chunking(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    @property
    def embedding_model(self) -> str:
        if self.provider == "openai":
            return self.openai_embedding_model
        return self.ollama_embedding_model

    @property
    def chat_model(self) -> str:
        if self.provider == "openai":
            return self.openai_chat_model
        return self.ollama_chat_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
