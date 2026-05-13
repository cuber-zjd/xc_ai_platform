import os
from pathlib import Path
from typing import List, Union

from pydantic import AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Platform"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[Union[str, AnyHttpUrl]] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
    ]

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

    # OnlyOffice Document Server
    ONLYOFFICE_SERVER_URL: str = "http://192.168.14.44:9509"
    ONLYOFFICE_JWT_SECRET: str = "ai_platform_onlyoffice_secret"

    # FineReport
    FINEREPORT_PREVIEW_BASE_URL: str = ""
    FR_AI_FINEREPORT_DB_NAME: str = "XcTest"
    FR_AI_SQLSERVER_ENABLED: bool = False
    FR_AI_SQLSERVER_HOST: str = ""
    FR_AI_SQLSERVER_PORT: int = 1433
    FR_AI_SQLSERVER_DATABASE: str = ""
    FR_AI_SQLSERVER_USER: str = ""
    FR_AI_SQLSERVER_PASSWORD: str = ""
    FR_AI_SQLSERVER_ODBC_DRIVER: str = "SQL Server"
    FR_AI_SQLSERVER_QUERY_TIMEOUT_SECONDS: int = 10
    FR_AI_SQLSERVER_MAX_ROWS: int = 20

    # Security
    SECRET_KEY: str = "change_this_to_a_secure_random_string_in_production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days
    MCP_API_KEY: str = ""  # MCP 服务认证密钥，留空则开发环境放行
    EXTERNAL_API_KEYS: List[str] = ["default_ai_sign_key_1", "default_ai_sign_key_2"] # 外部调用统一认证密钥


    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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

if settings.LANGFUSE_PUBLIC_KEY:
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
if settings.LANGFUSE_SECRET_KEY:
    os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
if settings.LANGFUSE_HOST:
    os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
os.environ["LANGFUSE_ENVIRONMENT"] = "default"
