import sys
from pathlib import Path

BACKEND_DIR = str(Path(__file__).resolve().parents[1])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[3] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api.") or m == "main":
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def test_main_basic():
    """Basic unit test scaffold for main."""
    assert True
