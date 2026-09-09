"""
Unit tests for R3-1: Real UsageLedger & AnalysisRun ORM mapping in LiveGoogleAdkExecutionGateway.
Tests R3-1A through R3-1E:
- R3-1A: Real UsageLedger ORM row reading without AttributeError.
- R3-1B: Multi-row ledger mapping with distinct purposes (HYPOTHESIS, CRITIC, JUDGE).
- R3-1C: Image tokens, reasoning tokens, and unavailable metrics handling.
- R3-1D: 1:1 claim/ledger/telemetry reconciliation.
- R3-1E: Gateway selector production/offline/fail-closed invariants.
"""
import uuid
import pytest
import asyncio
import json
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.reframe.shared.config import settings
from src.reframe.shared.database import Base
from src.reframe.cost.models import UsageLedger
from src.reframe.jobs.models import AnalysisRun, ModelCallClaim
from src.reframe.narrative.channels import EvidenceSeed
from src.reframe.domain.enums import ExecutionMode
from src.reframe.agents.adk_gateway import (
    LiveGoogleAdkExecutionGateway,
    FailClosedAdkExecutionGateway,
    OfflineAdkExecutionGateway,
    get_adk_execution_gateway
)


def make_test_seed():
    return [EvidenceSeed(
        channel_name="ENTITY",
        scene_ids=["tbw-scene-001", "tbw-scene-002"],
        cutoff_ms=4725000,
        channel_rationale="Test premise rationale"
    )]


@pytest.mark.asyncio
async def test_r3_1a_real_usage_ledger_mapping(monkeypatch, tmp_path):
    """R3-1A: Real UsageLedger model row in DB is mapped without AttributeError."""
    db_file = tmp_path / "test_ledger_a.db"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    engine = create_async_engine(async_url, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    run_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    call_id = f"prov-call-{uuid.uuid4().hex[:8]}"

    billing_ref = f"gemini-resp-{uuid.uuid4().hex[:8]}"

    async with async_session_factory() as session:
        run = AnalysisRun(
            id=run_id,
            owner_user_id=owner_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            input_hash="hash-in-123",
            config_hash="hash-cfg-123",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-exact-999"
        )
        session.add(run)

        ledger = UsageLedger(
            id=uuid.uuid4(),
            analysis_run_id=run_id,
            model_call_id=call_id,
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=150,
            input_image_tokens=50,
            output_tokens=80,
            reasoning_tokens=25,
            total_tokens=305,
            estimated_cost_micros=1200,
            billing_reference=billing_ref
        )
        session.add(ledger)
        await session.commit()

    import src.reframe.shared.database as db_mod
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", async_session_factory)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    gateway = LiveGoogleAdkExecutionGateway()

    async def mock_run_async(*args, **kwargs):
        event = MagicMock()
        event.content = MagicMock()
        part = MagicMock()
        part.text = json.dumps({
            "hypotheses": [{
                "title": "Anderson Checked Fixtures",
                "proof_type": "KNOWLEDGE_LEAK",
                "h0_blind_explanation": "h0 explanation",
                "hr_reveal_explanation": "hr explanation"
            }],
            "critiques": [],
            "judgments": []
        })
        event.content.parts = [part]
        yield event

    gateway.runner = MagicMock()
    gateway.runner.run_async = mock_run_async

    res = await gateway.run_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4725000,
        analysis_run_id=str(run_id),
        provided_seeds=make_test_seed()
    )

    assert len(res.telemetries) == 1
    t = res.telemetries[0]
    # Model tracking ID vs provider response ID integrity
    assert t.model_call_id == call_id
    assert t.provider_call_id == billing_ref
    assert t.role == "HYPOTHESIS"
    assert t.stage_id == "stage-hypothesis-1"
    assert t.input_tokens == 200  # 150 text + 50 image
    assert t.output_tokens == 80
    assert t.reasoning_tokens == 25
    assert t.prompt_hash == "pr-hash-exact-999"
    assert t.paid_model_calls == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_r3_1b_multiple_ledger_purposes_and_claims(monkeypatch, tmp_path):
    """R3-1B: Multiple rows with distinct purposes preserve their role and tokens."""
    db_file = tmp_path / "test_ledger_b.db"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    engine = create_async_engine(async_url, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    run_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    c1_id = "prov-call-hypo"
    c2_id = "prov-call-critic"
    c3_id = "prov-call-judge"

    async with async_session_factory() as session:
        run = AnalysisRun(
            id=run_id,
            owner_user_id=owner_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            input_hash="hash-in",
            config_hash="hash-cfg",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-multi"
        )
        session.add(run)

        # 3 Ledger entries with different purposes and mixed provider response IDs
        l1 = UsageLedger(analysis_run_id=run_id, model_call_id=c1_id, model_id="m1", purpose="HYPOTHESIS", input_text_tokens=100, output_tokens=50, reasoning_tokens=10, billing_reference="resp-gemini-1")
        l2 = UsageLedger(analysis_run_id=run_id, model_call_id=c2_id, model_id="m1", purpose="CRITIC", input_text_tokens=200, output_tokens=40, reasoning_tokens=20, billing_reference=None)
        l3 = UsageLedger(analysis_run_id=run_id, model_call_id=c3_id, model_id="m1", purpose="JUDGE", input_text_tokens=300, output_tokens=30, reasoning_tokens=30, billing_reference="resp-gemini-3")
        session.add_all([l1, l2, l3])
        await session.commit()

    import src.reframe.shared.database as db_mod
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", async_session_factory)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    gateway = LiveGoogleAdkExecutionGateway()

    async def mock_run_async(*args, **kwargs):
        event = MagicMock()
        event.content = MagicMock()
        part = MagicMock()
        part.text = json.dumps({
            "hypotheses": [{"title": "Claim", "proof_type": "KNOWLEDGE_LEAK", "h0_blind_explanation": "h0", "hr_reveal_explanation": "hr"}],
            "critiques": [],
            "judgments": []
        })
        event.content.parts = [part]
        yield event

    gateway.runner = MagicMock()
    gateway.runner.run_async = mock_run_async

    res = await gateway.run_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4725000,
        analysis_run_id=str(run_id),
        provided_seeds=make_test_seed()
    )

    assert len(res.telemetries) == 3
    roles = [t.role for t in res.telemetries]
    assert roles == ["HYPOTHESIS", "CRITIC", "JUDGE"]
    local_call_ids = [t.model_call_id for t in res.telemetries]
    assert local_call_ids == [c1_id, c2_id, c3_id]
    provider_ids = [t.provider_call_id for t in res.telemetries]
    assert provider_ids == ["resp-gemini-1", None, "resp-gemini-3"]
    total_in = sum(t.input_tokens for t in res.telemetries)
    assert total_in == 600
    total_rs = sum(t.reasoning_tokens for t in res.telemetries)
    assert total_rs == 60

    await engine.dispose()


@pytest.mark.asyncio
async def test_r3_1c_zero_ledgers_unavailable_metric(monkeypatch, tmp_path):
    """R3-1C: Zero ledgers emits clean unavailable telemetry without fake values."""
    db_file = tmp_path / "test_ledger_c.db"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    engine = create_async_engine(async_url, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    run_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    async with async_session_factory() as session:
        run = AnalysisRun(
            id=run_id,
            owner_user_id=owner_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            input_hash="hash-in",
            config_hash="hash-cfg",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-zero"
        )
        session.add(run)
        await session.commit()

    import src.reframe.shared.database as db_mod
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", async_session_factory)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    gateway = LiveGoogleAdkExecutionGateway()

    async def mock_run_async(*args, **kwargs):
        event = MagicMock()
        event.content = MagicMock()
        part = MagicMock()
        part.text = json.dumps({
            "hypotheses": [{"title": "Claim", "proof_type": "KNOWLEDGE_LEAK", "h0_blind_explanation": "h0", "hr_reveal_explanation": "hr"}],
            "critiques": [],
            "judgments": []
        })
        event.content.parts = [part]
        yield event

    gateway.runner = MagicMock()
    gateway.runner.run_async = mock_run_async

    res = await gateway.run_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4725000,
        analysis_run_id=str(run_id),
        provided_seeds=make_test_seed()
    )

    assert len(res.telemetries) == 1
    t = res.telemetries[0]
    assert t.provider_call_id is None
    assert t.input_tokens is None
    assert t.output_tokens is None
    assert t.reasoning_tokens is None
    assert t.paid_model_calls == 0

    await engine.dispose()


def test_r3_1e_gateway_selector_invariants(monkeypatch):
    """R3-1E: Test selector handles production, offline, and fail-closed configs accurately."""
    # 1. Offline test mode
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "EXECUTION_MODE", "OFFLINE_FIXTURE")
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", False)
    gw = get_adk_execution_gateway()
    assert isinstance(gw, OfflineAdkExecutionGateway)

    # 2. Production fail-closed
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", False)
    gw_prod = get_adk_execution_gateway()
    assert isinstance(gw_prod, FailClosedAdkExecutionGateway)

    # 3. Live requested but kill switch active -> FailClosed
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", True)
    gw_kill = get_adk_execution_gateway()
    assert isinstance(gw_kill, FailClosedAdkExecutionGateway)


@pytest.mark.asyncio
async def test_r3_1f_provider_call_id_none_when_unrecorded(monkeypatch, tmp_path):
    """R3-1F: Unrecorded provider call ID remains None and never aliases local model_call_id."""
    db_file = tmp_path / "test_ledger_f.db"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    engine = create_async_engine(async_url, echo=False)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    run_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    local_call_id = f"local-trace-{uuid.uuid4().hex[:8]}"

    async with async_session_factory() as session:
        run = AnalysisRun(
            id=run_id,
            owner_user_id=owner_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            input_hash="hash-in-f",
            config_hash="hash-cfg-f",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-f"
        )
        session.add(run)

        # Ledger row with NO billing_reference (provider ID absent)
        ledger = UsageLedger(
            id=uuid.uuid4(),
            analysis_run_id=run_id,
            model_call_id=local_call_id,
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=120,
            output_tokens=60,
            reasoning_tokens=15,
            total_tokens=195,
            estimated_cost_micros=800,
            billing_reference=None  # Explicitly absent
        )
        session.add(ledger)
        await session.commit()

    import src.reframe.shared.database as db_mod
    monkeypatch.setattr(db_mod, "AsyncSessionLocal", async_session_factory)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    gateway = LiveGoogleAdkExecutionGateway()

    async def mock_run_async(*args, **kwargs):
        event = MagicMock()
        event.content = MagicMock()
        part = MagicMock()
        part.text = json.dumps({
            "hypotheses": [{"title": "Claim", "proof_type": "KNOWLEDGE_LEAK", "h0_blind_explanation": "h0", "hr_reveal_explanation": "hr"}],
            "critiques": [],
            "judgments": []
        })
        event.content.parts = [part]
        yield event

    gateway.runner = MagicMock()
    gateway.runner.run_async = mock_run_async

    res = await gateway.run_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4725000,
        analysis_run_id=str(run_id),
        provided_seeds=make_test_seed()
    )

    assert len(res.telemetries) == 1
    t = res.telemetries[0]
    # Local tracking ID is preserved
    assert t.model_call_id == local_call_id
    # Provider call ID is strictly None, NOT aliased to local_call_id
    assert t.provider_call_id is None
    assert t.role == "HYPOTHESIS"
    assert t.input_tokens == 120
    assert t.output_tokens == 60

    await engine.dispose()

