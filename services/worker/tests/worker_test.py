import os
import sys
import pytest

# Ensure worker directory is in sys.path for scanning imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_worker_basic():
    """Basic unit test scaffold for worker."""
    assert True


@pytest.mark.asyncio
async def test_safe_cron_job_wrapper(caplog):
    import logging
    import sys
    import os

    # Temporarily remove all tests directories from sys.path to avoid scanners/jobs collisions
    matching_paths = [p for p in sys.path if "tests" in p]
    for p in matching_paths:
        sys.path.remove(p)

    tests_path = os.path.dirname(__file__)
    worker_path = os.path.abspath(os.path.join(tests_path, ".."))
    sys.path.insert(0, worker_path)

    # Invalidate sys.modules scanners and jobs if they were cached from tests
    for mod_name in ["scanners", "jobs"]:
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    try:
        from services.worker.worker import safe_cron_job
    finally:
        # Restore sys.path
        for p in matching_paths:
            sys.path.append(p)

    # A mock cron function that raises an exception
    async def mock_failing_cron(ctx):
        raise ValueError("Simulated connection or Redis timeout")

    # Wrap the cron function
    wrapped = safe_cron_job(mock_failing_cron)

    # Invoke the wrapped function and verify it does not raise an exception
    caplog.clear()
    await wrapped("mock_ctx")

    # Check that it logged the error properly
    error_logs = [
        r
        for r in caplog.records
        if "Cron job failed with unhandled exception" in r.message
    ]
    assert len(error_logs) == 1
    assert error_logs[0].levelno == logging.ERROR
    assert (
        getattr(error_logs[0], "fields", {}).get("error")
        == "Simulated connection or Redis timeout"
    )
