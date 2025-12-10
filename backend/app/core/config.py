from typing import List, Union
from pydantic import AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Platform"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "ai_platform"
    POSTGRES_PORT: int = 9500
    sqlalchemy_database_uri: Union[PostgresDsn, str] = ""

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 9501

    # Milvus
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 9504

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9502"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "ai-platform-files"

    # LangFuse
    LANGFUSE_PUBLIC_KEY: str = "pk-lf-..."
    LANGFUSE_SECRET_KEY: str = "sk-lf-..."
    LANGFUSE_HOST: str = "http://localhost:9506"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")

    def compute_database_url(self):
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

settings = Settings()
settings.sqlalchemy_database_uri = str(settings.compute_database_url()) # Pydantic v2 fix
