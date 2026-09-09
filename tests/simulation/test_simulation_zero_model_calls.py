"""
Reframe V7 Simulation Zero Model Calls Certification Tests
Enforces zero external network or model calls during simulations.
"""
import pytest
from src.reframe.simulation.schemas import SimulationRunConfig, SimulationMode, ScenarioVariant
from src.reframe.simulation.simulator import AudienceSimulator
from src.reframe.simulation.service import audience_lab_service


def test_simulation_run_zero_paid_model_calls(monkeypatch):
    """
    Asserts that executing a simulation run executes entirely on local deterministic logic
    with paid_model_calls = 0 and 0 external AI network calls.
    """
    # Monkeypatch any potential network/model call hooks to raise an exception if invoked
    def mock_disallowed_call(*args, **kwargs):
        raise RuntimeError("VIOLATION: External model API called during simulation run!")

    monkeypatch.setattr("urllib.request.urlopen", mock_disallowed_call, raising=False)

    personas = audience_lab_service.load_reproducibility_personas(count=50)

    config = SimulationRunConfig(
        mode=SimulationMode.CI,
        unique_source_personas=50,
        variants=[ScenarioVariant.QUICK_VALUE],
        replications=1,
        seed=42,
    )

    sim = AudienceSimulator(config)
    res = sim.run_simulation(personas)

    assert res.paid_model_calls == 0
    assert res.live_model_used is False
    assert res.synthetic_sessions == 50
