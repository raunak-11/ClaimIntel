import os
import sys

import pytest

# Make backend/ importable the same way the app imports it (flat module names).
# dev/tests/conftest.py -> repo root is two levels up (was one, before tests/
# moved under dev/).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "backend"))


@pytest.fixture(autouse=True)
def _isolated_oem_catalog(tmp_path, monkeypatch):
    """Point the OEM price catalogue at an empty per-test file.

    The real catalogue is committed data and the pricing engine reads it FIRST
    (and writes back to it), so without this every pricing test would depend on
    whatever the catalogue holds today — and a test that prices a part would
    edit the committed file. Tests that want catalogue entries write them.
    """
    from services import oem_catalog
    monkeypatch.setattr(oem_catalog, "OEM_CATALOG_PATH", str(tmp_path / "oem_price_catalog.json"))
    oem_catalog.reload()
    yield
    oem_catalog.reload()
