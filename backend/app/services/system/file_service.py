import asyncio
import io
from datetime import timedelta
from minio import Minio
from app.core.config import settings
from app.core.logger import logger

class FileService:
    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False # TODO: Set to True in production if HTTPS
        )
        self.bucket = settings.MINIO_BUCKET_NAME
        self._bucket_ready = False
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> bool:
        if self._bucket_ready:
            return True
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
            self._bucket_ready = True
            return True
        except Exception as e:
            logger.warning(
                f"MinIO bucket check failed, file APIs may be unavailable: "
                f"endpoint={settings.MINIO_ENDPOINT}, bucket={self.bucket}, error={e}"
            )
            return False

    def _ensure_bucket_available(self) -> None:
        if not self._ensure_bucket_exists():
            raise RuntimeError(
                f"MinIO bucket unavailable: endpoint={settings.MINIO_ENDPOINT}, bucket={self.bucket}"
            )

    async def upload_file(self, file_data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        """
        Uploads bytes to MinIO. Returns the object name.
        """
        try:
            self._ensure_bucket_available()
            file_stream = io.BytesIO(file_data)
            length = len(file_data)
            
            # Wrap synchronous MinIO call
            await asyncio.to_thread(
                self.client.put_object,
                bucket_name=self.bucket,
                object_name=object_name,
                data=file_stream,
                length=length,
                content_type=content_type
            )
            logger.info(f"Uploaded file to MinIO: {object_name}")
            return object_name
        except Exception as e:
            logger.error(f"Failed to upload file {object_name}: {e}")
            raise e

    async def get_presigned_url(self, object_name: str, expires: timedelta = timedelta(hours=1)) -> str:
        """
        Generates a presigned URL for frontend access.
        """
        try:
            self._ensure_bucket_available()
            url = await asyncio.to_thread(
                self.client.presigned_get_object,
                bucket_name=self.bucket,
                object_name=object_name,
                expires=expires
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_name}: {e}")
            raise e

    async def download_file(self, object_name: str) -> bytes:
        """
        Downloads file content as bytes (for backend processing/OCR).
        """
        try:
            self._ensure_bucket_available()
            response = await asyncio.to_thread(
                self.client.get_object,
                bucket_name=self.bucket,
                object_name=object_name
            )
            try:
                data = response.read()
                return data
            finally:
                response.close()
                response.release_conn()
        except Exception as e:
            logger.error(f"Failed to download file {object_name}: {e}")
            raise e

# Singleton instance
file_service: FileService = FileService()
