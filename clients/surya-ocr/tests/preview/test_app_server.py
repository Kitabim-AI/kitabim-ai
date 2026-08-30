from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from preview.app_server import create_landing_app


def test_index_returns_landing_page_html(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="landing"' in response.text
    assert 'id="processing"' in response.text
    assert 'id="review"' in response.text


def test_state_defaults_to_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json() == {"stage": "landing", "error": None}


def test_reset_from_landing_is_a_no_op(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert response.json() == {"stage": "landing"}
