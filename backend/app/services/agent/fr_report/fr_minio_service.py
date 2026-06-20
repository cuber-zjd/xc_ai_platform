import asyncio
import hashlib
import io
from dataclasses import dataclass

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logger import logger


@dataclass(frozen=True)
class FrMinIOObjectStat:
    object_name: str
    exists: bool
    etag: str | None = None
    last_modified: str | None = None
    size: int | None = None
    content_hash: str | None = None


class FrMinIOService:
    def __init__(self) -> None:
        self._client: Minio | None = None
        self.bucket = settings.FR_AI_MINIO_BUCKET_NAME

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> Minio:
        if not settings.FR_AI_MINIO_SECRET_KEY:
            raise RuntimeError("未配置 FR_AI_MINIO_SECRET_KEY，无法访问帆软 MinIO")
        return Minio(
            endpoint=settings.FR_AI_MINIO_ENDPOINT,
            access_key=settings.FR_AI_MINIO_ACCESS_KEY,
            secret_key=settings.FR_AI_MINIO_SECRET_KEY,
            secure=settings.FR_AI_MINIO_SECURE,
        )

    async def list_objects(self, prefix: str) -> list:
        return await asyncio.to_thread(
            lambda: list(
                self.client.list_objects(
                    self.bucket,
                    prefix=prefix,
                    recursive=True,
                )
            )
        )

    async def stat_object(self, object_name: str):
        return await asyncio.to_thread(
            self.client.stat_object,
            bucket_name=self.bucket,
            object_name=object_name,
        )

    async def object_exists(self, object_name: str) -> bool:
        try:
            await self.stat_object(object_name)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            raise

    async def stat_object_safe(self, object_name: str, include_hash: bool = False) -> FrMinIOObjectStat:
        try:
            stat = await self.stat_object(object_name)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return FrMinIOObjectStat(object_name=object_name, exists=False)
            raise
        content_hash = None
        if include_hash:
            content_hash = hashlib.sha256(await self.download_file(object_name)).hexdigest()
        return FrMinIOObjectStat(
            object_name=object_name,
            exists=True,
            etag=getattr(stat, "etag", None),
            last_modified=str(getattr(stat, "last_modified", "") or "") or None,
            size=getattr(stat, "size", None),
            content_hash=content_hash,
        )

    async def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        try:
            await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.bucket,
                object_name=object_name,
                data=io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
            )
            logger.info(f"Uploaded FineReport artifact to MinIO: {object_name}")
            return object_name
        except S3Error as exc:
            logger.error(f"Failed to upload FineReport artifact {object_name}: {exc}")
            raise

    async def download_file(self, object_name: str) -> bytes:
        response = await asyncio.to_thread(
            self.client.get_object,
            bucket_name=self.bucket,
            object_name=object_name,
        )
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def copy_object_by_download(self, source_object_name: str, target_object_name: str) -> str:
        data = await self.download_file(source_object_name)
        return await self.upload_file(data, target_object_name, "application/octet-stream")

    async def delete_object(self, object_name: str) -> None:
        await asyncio.to_thread(
            self.client.remove_object,
            bucket_name=self.bucket,
            object_name=object_name,
        )


fr_minio_service = FrMinIOService()
