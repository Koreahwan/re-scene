"""
Reframe V7 Simulation Persona Import Unit Tests
Validates Nemotron-Personas-USA sample parsing, adult filtering (18+), pseudonymization stability,
census region mapping, and order-invariance of hash-priority derived sampling.
Zero External Generative Model Calls.
"""
import pytest
import heapq
import random
from src.reframe.simulation.persona_adapter import (
    persona_adapter,
    US_CENSUS_REGIONS,
    STATE_FULL_TO_ABBR,
)
from src.reframe.simulation.schemas import DerivedPersonaProfile
from tools.simulation.import_nemotron_personas import compute_sample_priority


def test_pseudonymize_persona_id_stability():
    raw_uuid_1 = "nemotron_000001"
    raw_uuid_2 = "nemotron_000002"

    hash_1a = persona_adapter.compute_persona_hash(raw_uuid_1)
    hash_1b = persona_adapter.compute_persona_hash(raw_uuid_1)
    hash_2 = persona_adapter.compute_persona_hash(raw_uuid_2)

    assert hash_1a == hash_1b
    assert hash_1a != hash_2
    assert len(hash_1a) == 64  # SHA-256 hex string


def test_census_region_categorization():
    assert persona_adapter.get_census_region("NY") == "Northeast"
    assert persona_adapter.get_census_region("CA") == "West"
    assert persona_adapter.get_census_region("TX") == "South"
    assert persona_adapter.get_census_region("IL") == "Midwest"
    assert persona_adapter.get_census_region("ZZ") == "National"


def test_occupation_and_education_categorization():
    assert persona_adapter.categorize_occupation("Senior Software Engineer") == "Tech & Engineering"
    assert persona_adapter.categorize_occupation("Film Professor") == "Education & Research"
    assert persona_adapter.categorize_occupation("Retail Associate") == "Trades & Services"

    assert persona_adapter.categorize_education("PhD in Cinema Studies") == "Doctorate / Professional"
    assert persona_adapter.categorize_education("Bachelor of Arts") == "Bachelor's"
    assert persona_adapter.categorize_education("Some College") == "Some College / Associate"
    assert persona_adapter.categorize_education("High School Diploma") == "High School / GED"


def test_adapt_row_valid_adult():
    raw_row = {
        "uuid": "test_persona_001",
        "country": "United States",
        "name": "Sarah Connor",
        "age": 34,
        "sex": "Female",
        "state": "CA",
        "occupation": "Cybersecurity Analyst",
        "education_level": "Master of Science",
        "marital_status": "Single",
        "lens": "PROFESSIONAL",
    }
    persona, err = persona_adapter.adapt_row(raw_row, alias_index=1)
    assert err is None
    assert persona is not None
    assert isinstance(persona, DerivedPersonaProfile)
    assert persona.persona_id.startswith("us_pers_")
    assert persona.age_band == "25-34"
    assert persona.census_region == "West"
    assert persona.occupation_group == "Tech & Engineering"
    assert persona.education_group == "Master's"


def test_adapt_row_filters_underage():
    raw_minor = {
        "uuid": "minor_001",
        "country": "USA",
        "name": "Tommy",
        "age": 16,
        "sex": "Male",
        "state": "TX",
    }
    persona, err = persona_adapter.adapt_row(raw_minor, alias_index=2)
    assert persona is None
    assert err == "UNDER_18"


def test_derived_cache_order_invariance():
    """
    Verifies that sampling a derived persona cache using source_persona_id_hash
    produces the EXACT same subset and ordered sequence regardless of the input order.
    """
    dataset_id = "nvidia/Nemotron-Personas-USA"
    revision = "5b4cd35ab46490c1da1bd2b5a2324d6f871be180"
    seed = 42
    sample_size = 10

    # Build 30 test personas
    personas = [
        DerivedPersonaProfile(
            persona_id=f"us_pers_{i:04d}",
            source_persona_id_hash=f"{i:064x}",
            locale="en_US",
            display_alias=f"Synthetic Fan {i:04d}",
            age_band="25-34",
            state="NY",
            census_region="Northeast",
            location_context="Metro",
            education_group="Bachelor's",
            occupation_group="Tech",
            sampling_weight=1.0,
            source_dataset=dataset_id,
            source_revision=revision,
        )
        for i in range(30)
    ]

    def _sample(items):
        reservoir = []
        for p in items:
            priority = compute_sample_priority(p.source_persona_id_hash, dataset_id, revision, seed)
            if len(reservoir) < sample_size:
                heapq.heappush(reservoir, (-priority, p.persona_id, p))
            elif priority < -reservoir[0][0]:
                heapq.heapreplace(reservoir, (-priority, p.persona_id, p))
        return [p.persona_id for _, _, p in sorted(reservoir, key=lambda x: -x[0])]

    result_forward = _sample(personas)

    # Reverse order
    personas_rev = list(reversed(personas))
    result_reversed = _sample(personas_rev)

    # Shuffled order
    rng = random.Random(12345)
    personas_shuffled = list(personas)
    rng.shuffle(personas_shuffled)
    result_shuffled = _sample(personas_shuffled)

    assert result_forward == result_reversed
    assert result_forward == result_shuffled
    assert len(result_forward) == sample_size
