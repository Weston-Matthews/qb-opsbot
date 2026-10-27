import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "samples"))

from qb_opsbot import settings  # noqa: E402


@pytest.fixture
def config():
    return settings.load_config(os.path.join(ROOT, "config.example.json"), reload=True)


@pytest.fixture
def log_loc(tmp_path):
    return str(tmp_path / "log.txt")
