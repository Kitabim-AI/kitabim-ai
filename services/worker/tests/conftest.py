"""Make `pytest services/worker/tests/` work from the repo root.

Worker modules import `services.worker...` (repo root) and `app...`
(packages/backend-core); in Docker the image puts both on the path, but a
local pytest run doesn't, so collection failed with ModuleNotFoundError.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _path in (_REPO_ROOT, _REPO_ROOT / "packages" / "backend-core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
