from __future__ import annotations

import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.storage")

class StorageProvider(ABC):
    """Base abstract class for storage providers"""
    
    @abstractmethod
    async def upload_file(self, local_path: Path, remote_path: str) -> str:
        """Upload a local file to storage and return its identifier/URL"""
        pass

    @abstractmethod
    async def download_file(self, remote_path: str, local_path: Path) -> None:
        """Download a file from storage to a local path"""
        pass

    @abstractmethod
    async def delete_file(self, remote_path: str) -> None:
        """Delete a file from storage"""
        pass

    @abstractmethod
    def get_public_url(self, remote_path: str) -> str:
        """Get a public URL for the file"""
        pass

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """Check if a file exists in storage"""
        pass


class FileSystemStorageProvider(StorageProvider):
    """Legacy storage provider using local filesystem"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _get_full_path(self, remote_path: str) -> Path:
        return self.base_dir / remote_path

    async def upload_file(self, local_path: Path, remote_path: str) -> str:
        dest_path = self._get_full_path(remote_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest_path)
        return remote_path

    async def download_file(self, remote_path: str, local_path: Path) -> None:
        src_path = self._get_full_path(remote_path)
        if not src_path.exists():
            raise FileNotFoundError(f"Source file {src_path} does not exist")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, local_path)

    async def delete_file(self, remote_path: str) -> None:
        path = self._get_full_path(remote_path)
        if path.exists():
            path.unlink()

    def get_public_url(self, remote_path: str) -> str:
        # Assuming covers are served via /api/covers route
        if remote_path.startswith("covers/"):
            return f"/api/covers/{remote_path.replace('covers/', '')}"
        return f"/api/storage/{remote_path}"

    def exists(self, remote_path: str) -> bool:
        return self._get_full_path(remote_path).exists()


class GCSStorageProvider(StorageProvider):
    """Google Cloud Storage provider with dual bucket support"""
    
    def __init__(self, data_bucket: str, media_bucket: str):
        from google.cloud import storage
        self.client = storage.Client()
        self.data_bucket_name = data_bucket
        self.media_bucket_name = media_bucket
        self.data_bucket = self.client.bucket(data_bucket)
        self.media_bucket = self.client.bucket(media_bucket)

    def _get_bucket_and_path(self, remote_path: str):
        """Helper to determine which bucket to use based on path prefix"""
        if remote_path.startswith("covers/"):
            return self.media_bucket, self.media_bucket_name, remote_path
        # Default all other paths (including uploads/) to the private data bucket
        return self.data_bucket, self.data_bucket_name, remote_path

    async def upload_file(self, local_path: Path, remote_path: str) -> str:
        bucket, bucket_name, final_path = self._get_bucket_and_path(remote_path)
        blob = bucket.blob(final_path)
        blob.upload_from_filename(str(local_path))
        log_json(logger, logging.INFO, "File uploaded to GCS", bucket=bucket_name, path=final_path)
        return remote_path

    async def download_file(self, remote_path: str, local_path: Path) -> None:
        bucket, bucket_name, final_path = self._get_bucket_and_path(remote_path)
        blob = bucket.blob(final_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        log_json(logger, logging.INFO, "File downloaded from GCS", bucket=bucket_name, path=final_path)

    async def delete_file(self, remote_path: str) -> None:
        bucket, bucket_name, final_path = self._get_bucket_and_path(remote_path)
        blob = bucket.blob(final_path)
        if blob.exists():
            blob.delete()
            log_json(logger, logging.INFO, "File deleted from GCS", bucket=bucket_name, path=final_path)

    def get_public_url(self, remote_path: str) -> str:
        bucket, bucket_name, final_path = self._get_bucket_and_path(remote_path)
        # For the media bucket, return the direct public URL
        if bucket_name == self.media_bucket_name:
            return f"https://storage.googleapis.com/{bucket_name}/{final_path}"
        # For the private bucket, we don't have a simple public URL (would need signed URLs)
        return f"/api/storage/{remote_path}"

    def exists(self, remote_path: str) -> bool:
        bucket, _, final_path = self._get_bucket_and_path(remote_path)
        blob = bucket.blob(final_path)
        return blob.exists()


def get_storage_provider() -> StorageProvider:
    """Factory to get the configured storage provider"""
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    
    if backend == "gcs":
        data_bucket = os.getenv("GCS_DATA_BUCKET")
        media_bucket = os.getenv("GCS_MEDIA_BUCKET")
        if not data_bucket or not media_bucket:
            raise ValueError("GCS_DATA_BUCKET and GCS_MEDIA_BUCKET are required when STORAGE_BACKEND=gcs")
        return GCSStorageProvider(data_bucket, media_bucket)
    
    # Default to local filesystem
    return FileSystemStorageProvider(settings.data_dir)

# Global storage instance
storage = get_storage_provider()
