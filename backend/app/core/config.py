from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # LLM — primary
    GROQ_API_KEY: str = Field(..., env="GROQ_API_KEY")
    # Embeddings + fallback LLM
    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")
    # Reranker
    COHERE_API_KEY: str = Field(default="", env="COHERE_API_KEY")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(default="", env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = Field(default="", env="GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = Field(default="", env="GOOGLE_REDIRECT_URI")

    # JWT
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_EXPIRE_MINUTES: int = Field(default=1440, env="JWT_EXPIRE_MINUTES")

    # Frontend
    FRONTEND_URL: str = Field(default="http://localhost:5173", env="FRONTEND_URL")

    # Database / Storage
    DATABASE_URL: str = Field(default="sqlite:///./data/scalerag.db", env="DATABASE_URL")
    SUPABASE_URL: str = Field(default="", env="SUPABASE_URL")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="", env="SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_ANON_KEY: str = Field(default="", env="SUPABASE_ANON_KEY")
    SUPABASE_STORAGE_BUCKET: str = Field(default="documents", env="SUPABASE_STORAGE_BUCKET")

    # App
    MAX_UPLOAD_SIZE_MB: int = Field(default=50, env="MAX_UPLOAD_SIZE_MB")
    TEMP_DIR: str = Field(default="./tmp", env="TEMP_DIR")
    DOCUMENT_PROCESSOR_WORKERS: int = Field(default=2, env="DOCUMENT_PROCESSOR_WORKERS")
    EMBEDDING_BATCH_SIZE: int = Field(default=100, env="EMBEDDING_BATCH_SIZE")
    EMBEDDING_TIMEOUT_SECONDS: int = Field(default=45, env="EMBEDDING_TIMEOUT_SECONDS")
    EMBEDDING_INTER_BATCH_DELAY_SECONDS: float = Field(
        default=0.1,
        env="EMBEDDING_INTER_BATCH_DELAY_SECONDS",
    )
    EMBEDDING_MAX_RETRIES: int = Field(default=3, env="EMBEDDING_MAX_RETRIES")
    EMBEDDING_RATE_LIMIT_RETRIES: int = Field(default=0, env="EMBEDDING_RATE_LIMIT_RETRIES")
    EMBEDDING_RATE_LIMIT_BASE_DELAY_SECONDS: int = Field(
        default=15,
        env="EMBEDDING_RATE_LIMIT_BASE_DELAY_SECONDS",
    )
    EMBEDDING_RATE_LIMIT_MAX_DELAY_SECONDS: int = Field(
        default=60,
        env="EMBEDDING_RATE_LIMIT_MAX_DELAY_SECONDS",
    )
    EMBEDDING_LOCAL_FALLBACK_ENABLED: bool = Field(
        default=True,
        env="EMBEDDING_LOCAL_FALLBACK_ENABLED",
    )

    # Rate limiting (requests per minute per user)
    RATE_LIMIT_RPM: int = Field(default=60, env="RATE_LIMIT_RPM")
    AUTH_RATE_LIMIT_RPM: int = Field(default=20, env="AUTH_RATE_LIMIT_RPM")
    UPLOAD_RATE_LIMIT_RPM: int = Field(default=12, env="UPLOAD_RATE_LIMIT_RPM")

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
