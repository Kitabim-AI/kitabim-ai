"""
Test Gemini Batch Client.

Run with: pytest packages/backend-core/tests/test_batch_client.py -v
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from google.genai import types

from app.services.gemini_batch_client import GeminiBatchClient


class TestGeminiBatchClient:
    """Test suite for GeminiBatchClient"""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Gemini client"""
        with patch('app.services.gemini_batch_client.genai.Client') as mock:
            client = GeminiBatchClient()
            yield client, mock

    def test_client_initialization(self, mock_client):
        """Test client initializes correctly"""
        client, mock_cls = mock_client
        assert client.client is not None
        assert client.api_key is not None

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_create_batch_job_success(self, mock_genai_client):
        """Test successful batch job creation"""
        # Setup mocks
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        # Mock file upload response
        mock_file_response = MagicMock()
        mock_file_response.name = "files/test-file-123"
        mock_client_instance.files.upload.return_value = mock_file_response

        # Mock batch create response
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/test-batch-456"
        mock_client_instance.batches.create.return_value = mock_batch_job

        # Test
        client = GeminiBatchClient()
        job_id, file_name = client.create_batch_job("/tmp/test.jsonl")

        # Assertions
        assert job_id == "batches/test-batch-456"
        assert file_name == "files/test-file-123"
        mock_client_instance.files.upload.assert_called_once()
        mock_client_instance.batches.create.assert_called_once()

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_create_embedding_batch_job_success(self, mock_genai_client):
        """Test successful embedding batch job creation"""
        # Setup mocks
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        # Mock file upload
        mock_file_response = MagicMock()
        mock_file_response.name = "files/embed-file-123"
        mock_client_instance.files.upload.return_value = mock_file_response

        # Mock batch create
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/embed-batch-456"
        mock_client_instance.batches.create_embeddings.return_value = mock_batch_job

        # Test
        client = GeminiBatchClient()
        job_id, file_name = client.create_embedding_batch_job("/tmp/embed.jsonl")

        # Assertions
        assert job_id == "batches/embed-batch-456"
        assert file_name == "files/embed-file-123"
        mock_client_instance.batches.create_embeddings.assert_called_once()

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_get_job_status(self, mock_genai_client):
        """Test getting job status"""
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        mock_job = MagicMock()
        mock_job.state = "SUCCEEDED"
        mock_client_instance.batches.get.return_value = mock_job

        client = GeminiBatchClient()
        status = client.get_job_status("batches/test-123")

        assert status == "SUCCEEDED"
        mock_client_instance.batches.get.assert_called_once_with(name="batches/test-123")

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_download_batch_output(self, mock_genai_client):
        """Test downloading batch output"""
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        # Mock job with output file
        mock_job = MagicMock()
        mock_job.dest = MagicMock()
        mock_job.dest.file_name = "files/output-123"
        mock_client_instance.batches.get.return_value = mock_job

        # Mock file download
        expected_content = b'{"result": "test"}'
        mock_client_instance.files.download.return_value = expected_content

        client = GeminiBatchClient()
        output = client.download_batch_output("batches/test-123")

        assert output == expected_content
        mock_client_instance.files.download.assert_called_once_with(file="files/output-123")

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_download_batch_output_no_dest(self, mock_genai_client):
        """Test downloading batch output when no destination file exists"""
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        # Mock job without output file
        mock_job = MagicMock()
        mock_job.dest = None
        mock_client_instance.batches.get.return_value = mock_job

        client = GeminiBatchClient()

        with pytest.raises(Exception, match="has no output file_name"):
            client.download_batch_output("batches/test-123")

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_delete_file(self, mock_genai_client):
        """Test deleting file from Gemini API"""
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        client = GeminiBatchClient()
        client.delete_file("files/test-123")

        mock_client_instance.files.delete.assert_called_once_with(name="files/test-123")

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_cancel_job(self, mock_genai_client):
        """Test canceling a batch job"""
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        client = GeminiBatchClient()
        client.cancel_job("batches/test-123")

        mock_client_instance.batches.delete.assert_called_once_with(name="batches/test-123")

    @patch('app.services.gemini_batch_client.genai.Client')
    def test_list_jobs(self, mock_genai_client):
        """Test listing batch jobs"""
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance

        mock_jobs = [MagicMock(), MagicMock()]
        mock_client_instance.batches.list.return_value = iter(mock_jobs)

        client = GeminiBatchClient()
        jobs = client.list_jobs()

        assert len(jobs) == 2
        mock_client_instance.batches.list.assert_called_once()
