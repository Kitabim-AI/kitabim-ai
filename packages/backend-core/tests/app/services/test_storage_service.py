import pytest
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.storage_service import FileSystemStorageProvider, GCSStorageProvider, get_storage_provider

@pytest.fixture
def temp_storage_dir(tmp_path):
    d = tmp_path / "storage"
    d.mkdir()
    return d

@pytest.fixture
def fs_provider(temp_storage_dir):
    return FileSystemStorageProvider(temp_storage_dir)

@pytest.mark.asyncio
async def test_fs_upload_file(fs_provider, tmp_path):
    local_file = tmp_path / "test.txt"
    local_file.write_text("hello")
    
    remote_path = "uploads/test.txt"
    await fs_provider.upload_file(local_file, remote_path)
    
    full_path = fs_provider.base_dir / remote_path
    assert full_path.exists()
    assert full_path.read_text() == "hello"

@pytest.mark.asyncio
async def test_fs_upload_bytes(fs_provider):
    data = b"binary data"
    remote_path = "data.bin"
    await fs_provider.upload_bytes(data, remote_path)
    
    full_path = fs_provider.base_dir / remote_path
    assert full_path.exists()
    assert full_path.read_bytes() == data

@pytest.mark.asyncio
async def test_fs_download_file(fs_provider, tmp_path):
    remote_path = "remote.txt"
    full_path = fs_provider.base_dir / remote_path
    full_path.write_text("remote content")
    
    local_path = tmp_path / "downloaded.txt"
    await fs_provider.download_file(remote_path, local_path)
    assert local_path.read_text() == "remote content"

@pytest.mark.asyncio
async def test_fs_read_bytes(fs_provider):
    remote_path = "test.bin"
    full_path = fs_provider.base_dir / remote_path
    full_path.write_bytes(b"bytes")
    
    assert await fs_provider.read_bytes(remote_path) == b"bytes"

@pytest.mark.asyncio
async def test_fs_delete_file(fs_provider):
    remote_path = "delete_me.txt"
    full_path = fs_provider.base_dir / remote_path
    full_path.write_text("data")
    
    await fs_provider.delete_file(remote_path)
    assert not full_path.exists()

def test_fs_get_public_url(fs_provider):
    assert fs_provider.get_public_url("covers/123.jpg") == "/api/covers/123.jpg"
    assert fs_provider.get_public_url("other/file.txt") == "/api/storage/other/file.txt"
    assert fs_provider.get_public_url("http://example.com") == "http://example.com"

@pytest.mark.asyncio
async def test_fs_list_files(fs_provider):
    (fs_provider.base_dir / "dir").mkdir(parents=True, exist_ok=True)
    (fs_provider.base_dir / "dir/f1.txt").write_text("1")
    (fs_provider.base_dir / "dir/f2.txt").write_text("2")
    
    files = await fs_provider.list_files("dir")
    assert len(files) == 2
    # The return is relative to base_dir
    assert "dir/f1.txt" in files or "dir/f1.txt" in [f.replace("\\", "/") for f in files]

@pytest.mark.asyncio
async def test_gcs_provider_mock():
    with patch("google.cloud.storage.Client") as mock_client:
        provider = GCSStorageProvider("data-bucket", "media-bucket")
        mock_bucket = mock_client.return_value.bucket.return_value
        mock_blob = mock_bucket.blob.return_value
        
        await provider.upload_bytes(b"data", "covers/test.jpg")
        assert mock_bucket.blob.called
        assert mock_blob.upload_from_string.called
        
        assert provider.get_gs_uri("test.txt") == "gs://data-bucket/test.txt"

def test_get_storage_provider():
    with patch.dict("os.environ", {"STORAGE_BACKEND": "local"}):
        # settings.data_dir is used
        p = get_storage_provider()
        assert isinstance(p, FileSystemStorageProvider)
    
    with patch.dict("os.environ", {"STORAGE_BACKEND": "gcs", "GCS_DATA_BUCKET": "d", "GCS_MEDIA_BUCKET": "m"}):
        with patch("google.cloud.storage.Client"):
            p = get_storage_provider()
            assert isinstance(p, GCSStorageProvider)
