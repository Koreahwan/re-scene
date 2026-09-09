"""
Legacy API Test Configuration
Enables legacy paid path flag for legacy test harness compatibility.
Zero Paid Model Calls.
"""
import pytest
from src.reframe.shared.config import settings


@pytest.fixture(autouse=True)
def enable_legacy_paid_path(monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_PAID_PATH_ENABLED", True)
