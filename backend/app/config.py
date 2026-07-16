from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:changeme@127.0.0.1:5440/medical_constructor",
        description="Async SQLAlchemy URL (asyncpg driver)",
    )
    cors_origins: str = Field(
        default="http://localhost:3008,http://127.0.0.1:3008,http://localhost:3000",
        description="Comma-separated browser origins for CORS",
    )

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    max_graph_nodes: int = 500
    max_graph_edges: int = 2000

    primary_llm_provider: str = Field(default="openai", description="gemini or openai")
    gemini_api_key: str = ""
    openai_api_key: str = ""
    gemini_models: str = "gemini-1.5-pro,gemini-1.5-flash"
    openai_models: str = "gpt-5.1"
    
    # Must match both the pgvector column dimension and ConceptMatcher output.
    embedding_model_name: str = "text-embedding-3-small"
    embedding_vector_dim: int = 1536
    embedding_batch_size: int = 64
    concept_similarity_threshold: float = 0.72
    openai_embedding_timeout: float = 8.0
    openai_embedding_max_retries: int = 0
    evaluation_embedding_timeout: float = 10.0
    concept_matcher_cache_ttl_seconds: float = 300.0

    enable_structlog: bool = False
    enable_prometheus: bool = True
    enable_otel: bool = False

    jwt_secret_key: str = Field(default="change-me-in-production-use-openssl-rand-hex-32", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    @field_validator("concept_similarity_threshold")
    @classmethod
    def threshold_in_unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("concept_similarity_threshold must be between 0 and 1")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Return the configured PostgreSQL URL without the async SQLAlchemy driver."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
