import asyncio
import os
import logging
from pathlib import Path
from app.core.config import settings
from app.services.storage_service import storage, GCSStorageProvider
from app.utils.observability import configure_logging

async def migrate_to_gcs():
    configure_logging()
    logger = logging.getLogger("app.migration")
    
    if not isinstance(storage, GCSStorageProvider):
        print("Error: STORAGE_BACKEND must be 'gcs' and GCS_DATA_BUCKET/GCS_MEDIA_BUCKET must be set to run migration.")
        return

    print(f"Starting migration to GCS buckets:")
    print(f" - Data Bucket: {settings.gcs_data_bucket}")
    print(f" - Media Bucket: {settings.gcs_media_bucket}")

    # Migrate Uploads
    uploads_dir = settings.uploads_dir
    if uploads_dir.exists():
        print(f"Migrating uploads from {uploads_dir}...")
        files = list(uploads_dir.glob("*.pdf"))
        print(f"Found {len(files)} PDFs.")
        for i, file_path in enumerate(files):
            remote_path = f"uploads/{file_path.name}"
            print(f" [{i+1}/{len(files)}] Uploading {file_path.name}...")
            try:
                await storage.upload_file(file_path, remote_path)
            except Exception as e:
                print(f"  FAILED to upload {file_path.name}: {e}")

    # Migrate Covers
    covers_dir = settings.covers_dir
    if covers_dir.exists():
        print(f"\nMigrating covers from {covers_dir}...")
        files = list(covers_dir.glob("*.jpg"))
        print(f"Found {len(files)} covers.")
        for i, file_path in enumerate(files):
            remote_path = f"covers/{file_path.name}"
            print(f" [{i+1}/{len(files)}] Uploading {file_path.name}...")
            try:
                await storage.upload_file(file_path, remote_path)
            except Exception as e:
                print(f"  FAILED to upload {file_path.name}: {e}")

    print("\nMigration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_to_gcs())
