import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pytest

from dentaldesk.knowledge import load_clinic
from dentaldesk.scenarios import load_suite

FIXTURE_CLINIC = REPO_ROOT / "knowledge" / "clinics" / "demo-smile-westlands.yaml"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def clinic():
    return load_clinic(FIXTURE_CLINIC)


@pytest.fixture(scope="session")
def suite():
    return load_suite()
