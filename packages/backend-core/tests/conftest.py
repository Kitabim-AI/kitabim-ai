import os
import pytest

# Force STORAGE_BACKEND to local for tests to avoid GCS initialization errors.
# This must happen before any service modules are imported.
os.environ["STORAGE_BACKEND"] = "local"
os.environ["ENVIRONMENT"] = "test"

@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    pass
