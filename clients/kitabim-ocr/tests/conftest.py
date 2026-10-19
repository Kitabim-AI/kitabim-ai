import pytest


@pytest.fixture(autouse=True)
def prevent_chandra_model_download(monkeypatch):
    """Safety guard: prevent tests from accidentally downloading the 10GB Chandra model."""

    def disallowed(*args, **kwargs):
        raise RuntimeError(
            "Attempted to load real Chandra model during testing. "
            "Please mock get_recognition_predictor or InferenceManager in your test."
        )

    try:
        import chandra.model.hf

        monkeypatch.setattr(chandra.model.hf, "load_model", disallowed)
    except (ImportError, AttributeError):
        pass

    try:
        import chandra.model

        monkeypatch.setattr(chandra.model, "load_model", disallowed)
    except (ImportError, AttributeError):
        pass
