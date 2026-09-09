"""The live verification contract, tested without provider calls."""
from types import SimpleNamespace
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.verify_live_services import budget_micros, validate_reading
from src.reframe.cost.invoker import verified_sdk_usage, ensure_model_location_supported
from src.reframe.cost.guard import PaidCallGuardException
from src.reframe.cost.pricing import pricing_registry
from src.reframe.shared.config import settings


@pytest.mark.parametrize('location', ['global', 'us', 'eu'])
def test_flash_supported_generation_locations(location):
    ensure_model_location_supported('gemini-3.6-flash', location)


def test_flash_regional_endpoint_is_rejected_before_generation():
    with pytest.raises(PaidCallGuardException, match='global, us, or eu'):
        ensure_model_location_supported('gemini-3.6-flash', 'us-central1')


def test_global_and_multiregion_billing_rates_remain_distinct(monkeypatch):
    monkeypatch.setattr(settings, 'GOOGLE_CLOUD_LOCATION', 'global')
    global_price = pricing_registry.get_pricing('gemini-3.6-flash')
    assert global_price.input_text_micro_rate == 0.75
    assert global_price.output_text_micro_rate == 3.75
    monkeypatch.setattr(settings, 'GOOGLE_CLOUD_LOCATION', 'us')
    regional_price = pricing_registry.get_pricing('gemini-3.6-flash')
    assert regional_price.input_text_micro_rate == 0.825
    assert regional_price.output_text_micro_rate == 4.125


def test_entrypoint_resolves_internal_modules_without_pytest_pythonpath():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    check = subprocess.run([sys.executable, '-c',
        "import runpy; runpy.run_path('scripts/verify_live_services.py'); import reframe.domain.models"],
        cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize('value', ['0', '-1', '1.01', 'NaN', 'Infinity'])
def test_verification_rejects_invalid_or_excessive_budget(value):
    with pytest.raises(ValueError):
        budget_micros(value)


def test_verification_budget_is_explicit_and_bounded():
    assert budget_micros('0.50') == 500000
    assert budget_micros('1') == 1000000


def test_generated_reading_must_cite_retrieved_evidence():
    assert validate_reading('{"analysis":"A cautious reading.","source_segment_ids":["segment-1"]}', {'segment-1'})
    with pytest.raises(ValueError):
        validate_reading('{"analysis":"Unrelated.","source_segment_ids":["future"]}', {'segment-1'})
    with pytest.raises(ValueError):
        validate_reading('{"status":"COMPLETED"}', {'segment-1'})


@pytest.mark.parametrize('usage', [None, SimpleNamespace(prompt_token_count=None, candidates_token_count=10),
                                  SimpleNamespace(prompt_token_count=10, candidates_token_count=None),
                                  SimpleNamespace(prompt_token_count=-1, candidates_token_count=10)])
def test_missing_sdk_usage_is_not_replaced_with_an_estimate(usage):
    with pytest.raises(RuntimeError, match='SDK_USAGE_MISSING'):
        verified_sdk_usage(SimpleNamespace(usage_metadata=usage))


def test_sdk_usage_is_preserved_including_reasoning():
    usage = SimpleNamespace(prompt_token_count=123, candidates_token_count=45, thoughts_token_count=67)
    assert verified_sdk_usage(SimpleNamespace(usage_metadata=usage)) == (123, 45, 67)
