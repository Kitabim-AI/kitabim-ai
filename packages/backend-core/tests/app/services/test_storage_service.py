import os
import sys
from unittest.mock import MagicMock
# Mock google.cloud to prevent credential errors during import
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.storage'] = MagicMock()

os.environ["STORAGE_BACKEND"] = "local"
import pytest
import shutil
from pathlib import Path
from app.services.storage_service import FileSystemStorageProvider

@pytest.fixture
def temp_storage(tmp_path):
    base_dir = tmp_path / "storage"
    base_dir.mkdir()
    return FileSystemStorageProvider(base_dir)

@pytest.mark.asyncio
async def test_filesystem_upload_bytes(temp_storage):
    data = b"hello world"
    path = "test/file.txt"
    returned_path = await temp_storage.upload_bytes(data, path)
    
    assert returned_path == path
    full_path = temp_storage.base_dir / path
    assert full_path.exists()
    assert full_path.read_bytes() == data

@pytest.mark.asyncio
async def test_filesystem_upload_file(temp_storage, tmp_path):
    local_file = tmp_path / "local.txt"
    local_file.write_text("file content")
    
    remote_path = "uploads/local.txt"
    await temp_storage.upload_file(local_file, remote_path)
    
    assert (temp_storage.base_dir / remote_path).exists()
    assert (temp_storage.base_dir / remote_path).read_text() == "file content"

@pytest.mark.asyncio
async def test_filesystem_read_bytes(temp_storage):
    path = "existing.bin"
    full_path = temp_storage.base_dir / path
    full_path.write_bytes(b"data")
    
    data = await temp_storage.read_bytes(path)
    assert data == b"data"

@pytest.mark.asyncio
async def test_filesystem_delete_file(temp_storage):
    path = "to_delete.txt"
    full_path = temp_storage.base_dir / path
    full_path.write_text("gone")
    
    assert full_path.exists()
    await temp_storage.delete_file(path)
    assert not full_path.exists()

def test_filesystem_get_public_url(temp_storage):
    assert temp_storage.get_public_url("covers/abc.jpg") == "/api/covers/abc.jpg"
    assert temp_storage.get_public_url("uploads/doc.pdf") == "/api/storage/uploads/doc.pdf"
    assert temp_storage.get_public_url("http://external.com/img.jpg") == "http://external.com/img.jpg"

@pytest.mark.asyncio
async def test_filesystem_list_files(temp_storage):
    await temp_storage.upload_bytes(b"1", "dir/a.txt")
    await temp_storage.upload_bytes(b"2", "dir/b.txt")
    await temp_storage.upload_bytes(b"3", "other/c.txt")
    
    files = await temp_storage.list_files("dir")
    assert len(files) == 2
    assert "dir/a.txt" in files
    assert "dir/b.txt" in files
