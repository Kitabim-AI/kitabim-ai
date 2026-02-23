"""Gemini Batch API Client using direct google-genai SDK"""
from __future__ import annotations

import logging
from typing import Optional, List
from google import genai
from google.genai import types
from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger(__name__)

class GeminiBatchClient:
    """
    Direct client for Gemini Batch API.
    LangChain doesn't support Batch API yet, so we use the official SDK.
    """

    def __init__(self):
        self.api_key = settings.gemini_api_key
        # Note: google-genai SDK use synchronous client by default, 
        # but we can use it in a thread pool or just accept its sync nature for management tasks.
        self.client = genai.Client(api_key=self.api_key)

    def create_batch_job(
        self, 
        input_file_path: str, 
        model: str = "gemini-3-flash-preview"
    ) -> tuple[str, str]:
        """
        Submits a batch job to Gemini using a local JSONL file.
        Uploads the file to Gemini File API first.
        Returns the job ID and the File API file name.
        """
        try:
            # 1. Upload to File API (required for Gemini API/AI Studio batches)
            log_json(logger, logging.INFO, "Uploading JSONL to Gemini File API", file=input_file_path)
            f_res = self.client.files.upload(
                file=input_file_path,
                config=types.UploadFileConfig(mime_type="application/json")
            )
            
            # 2. Create the batch job
            job = self.client.batches.create(
                model=model,
                src=f_res.name
            )
            log_json(logger, logging.INFO, "Gemini Batch Job created", 
                     remote_job_id=job.name, file=f_res.name)
            return job.name, f_res.name
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to create Gemini Batch Job", error=str(e))
            raise

    def create_embedding_batch_job(
        self,
        input_file_path: str,
        model: str = "models/gemini-embedding-001"
    ) -> tuple[str, str]:
        """
        Submits an embedding batch job using experimental create_embeddings.
        Returns the job ID and the File API file name.
        """
        try:
            # 1. Upload to File API
            f_res = self.client.files.upload(
                file=input_file_path,
                config=types.UploadFileConfig(mime_type="application/json")
            )

            # 2. Create embedding batch
            job = self.client.batches.create_embeddings(
                model=model,
                src=types.EmbeddingsBatchJobSource(file_name=f_res.name)
            )
            log_json(logger, logging.INFO, "Gemini Embedding Batch Job created", 
                     remote_job_id=job.name, file=f_res.name)
            return job.name, f_res.name
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to create Gemini Embedding Batch Job", error=str(e))
            raise

    def get_job(self, job_id: str) -> types.BatchJob:
        """
        Gets the full batch job object.
        """
        try:
            return self.client.batches.get(name=job_id)
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to get Gemini Batch Job", 
                     job_id=job_id, error=str(e))
            raise

    def get_job_status(self, job_id: str) -> str:
        """
        Gets the status of a batch job.
        Returns 'SUCCEEDED', 'FAILED', 'RUNNING', etc.
        """
        try:
            job = self.get_job(job_id)
            return job.state
        except Exception:
            return "UNKNOWN"

    def download_batch_output(self, job_name: str) -> bytes:
        """
        Downloads the output file for a completed batch job.
        """
        try:
            job = self.client.batches.get(name=job_name)
            if not job.dest or not getattr(job.dest, 'file_name', None):
                raise Exception(f"Batch job {job_name} has no output file_name")
            log_json(logger, logging.INFO, "Downloading batch output", job_id=job_name, file=job.dest.file_name)
            return self.client.files.download(file=job.dest.file_name)
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to download batch output", job_id=job_name, error=str(e))
            raise

    def delete_file(self, file_name: str) -> None:
        """
        Deletes a file from Gemini File API.
        """
        try:
            self.client.files.delete(name=file_name)
            log_json(logger, logging.INFO, "Deleted file from Gemini API", file=file_name)
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to delete file from Gemini API", file=file_name, error=str(e))

    def list_jobs(self) -> List[types.BatchJob]:
        """Lists recent batch jobs"""
        return list(self.client.batches.list())

    def cancel_job(self, job_id: str) -> None:
        """Cancels a batch job"""
        try:
            self.client.batches.delete(name=job_id)
            log_json(logger, logging.INFO, "Gemini Batch Job cancelled", job_id=job_id)
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to cancel Gemini Batch Job", 
                     job_id=job_id, error=str(e))
            raise
