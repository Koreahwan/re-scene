"""
Reframe V7 Synthetic Audience Lab Schemas
Type-safe definitions for simulation configurations, persona traits,
state machines, metrics, bottlenecks, sensitivity, and demand scenarios.
"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SimulationMode(str, Enum):
    CI = "CI"
    SMOKE = "SMOKE"
    DEMO_US = "DEMO_US"
    FULL_US = "FULL_US"
    MAX_SCALE = "MAX_SCALE"


class ScenarioVariant(str, Enum):
    QUICK_VALUE = "QUICK_VALUE"
    CURRENT_BASELINE = "CURRENT_BASELINE"
    EARLY_AUTH = "EARLY_AUTH"
    DEEP_ANALYSIS = "DEEP_ANALYSIS"
    COMMUNITY_FIRST = "COMMUNITY_FIRST"


class GoldenPathState(str, Enum):
    LANDING = "LANDING"
    FILM_HUB = "FILM_HUB"
    SPOILER_GATE = "SPOILER_GATE"
    REVEAL = "REVEAL"
    DEEP_REFRAME = "DEEP_REFRAME"
    REWATCH = "REWATCH"
    THEORY_LAB = "THEORY_LAB"
    THEORY_DRAFT = "THEORY_DRAFT"
    THEORY_VALIDATION = "THEORY_VALIDATION"
    COMMUNITY_READ = "COMMUNITY_READ"
    COMMUNITY_CREATE = "COMMUNITY_CREATE"
    COMMENT = "COMMENT"
    COUNTERCLAIM = "COUNTERCLAIM"
    MAGAZINE_READ = "MAGAZINE_READ"
    RETURN_VISIT = "RETURN_VISIT"
    EXIT = "EXIT"


class DropoffReason(str, Enum):
    VALUE_NOT_CLEAR = "VALUE_NOT_CLEAR"
    NO_RELEVANT_FILM = "NO_RELEVANT_FILM"
    SPOILER_FRICTION = "SPOILER_FRICTION"
    AUTH_FRICTION = "AUTH_FRICTION"
    CONTENT_TOO_DENSE = "CONTENT_TOO_DENSE"
    LOW_TRUST = "LOW_TRUST"
    NO_VERIFIED_PROOF = "NO_VERIFIED_PROOF"
    REWATCH_MEDIA_FRICTION = "REWATCH_MEDIA_FRICTION"
    MEDIA_LATENCY = "MEDIA_LATENCY"
    API_LATENCY = "API_LATENCY"
    THEORY_EFFORT = "THEORY_EFFORT"
    COMMUNITY_COLD_START = "COMMUNITY_COLD_START"
    NO_EVIDENCE_CONFIDENCE = "NO_EVIDENCE_CONFIDENCE"
    MAGAZINE_NOT_RELEVANT = "MAGAZINE_NOT_RELEVANT"
    ERROR = "ERROR"
    SESSION_COMPLETE = "SESSION_COMPLETE"


class FanDepth(str, Enum):
    CASUAL = "CASUAL"
    REGULAR = "REGULAR"
    DEEP_ANALYST = "DEEP_ANALYST"
    FILM_FORM_FAN = "FILM_FORM_FAN"
    THEORY_EXPLORER = "THEORY_EXPLORER"


class PersonaLens(str, Enum):
    GENERAL = "GENERAL"
    PROFESSIONAL = "PROFESSIONAL"
    ARTS = "ARTS"
    SPORTS = "SPORTS"
    TRAVEL = "TRAVEL"
    CULINARY = "CULINARY"


class TerminationReason(str, Enum):
    CONVERGED = "CONVERGED"
    MAX_SCALE_REACHED = "MAX_SCALE_REACHED"
    SOURCE_UNIVERSE_EXHAUSTED = "SOURCE_UNIVERSE_EXHAUSTED"
    SAMPLE_TARGET_REACHED = "SAMPLE_TARGET_REACHED"


# ---------------------------------------------------------------------------
# Fan Traits & Personas
# ---------------------------------------------------------------------------

class SyntheticFanTraits(BaseModel):
    fan_depth: FanDepth = FanDepth.REGULAR
    spoiler_tolerance: float = Field(ge=0.0, le=1.0)
    rewatch_affinity: float = Field(ge=0.0, le=1.0)
    reading_patience: float = Field(ge=0.0, le=1.0)
    theory_writing_propensity: float = Field(ge=0.0, le=1.0)
    community_participation: float = Field(ge=0.0, le=1.0)
    evidence_preference: float = Field(ge=0.0, le=1.0)
    digital_comfort: float = Field(ge=0.0, le=1.0)
    trust_in_ai_analysis: float = Field(ge=0.0, le=1.0)
    moderation_sensitivity: float = Field(ge=0.0, le=1.0)
    return_intent: float = Field(ge=0.0, le=1.0)
    magazine_reading_affinity: float = Field(ge=0.0, le=1.0)

    behavioral_ground_truth: bool = False
    demographic_behavior_inference: bool = False
    trait_assignment_seed: int = 42
    trait_policy_version: str = "reframe_us_fan_traits_v1"


class DerivedPersonaProfile(BaseModel):
    persona_id: str
    source_persona_id_hash: str
    locale: str = "en_US"
    display_alias: str
    age_band: str
    state: str
    census_region: str
    location_context: str
    education_group: str
    occupation_group: str
    sampling_weight: float = 1.0
    safe_interest_tags: List[str] = Field(default_factory=list)
    available_persona_lenses: List[PersonaLens] = Field(default_factory=list)
    source_dataset: str = "nvidia/Nemotron-Personas-USA"
    source_revision: str = "5b4cd35ab46490c1da1bd2b5a2324d6f871be180"
    traits: Optional[SyntheticFanTraits] = None


# ---------------------------------------------------------------------------
# Simulation Config & Traces
# ---------------------------------------------------------------------------

class ScenarioConfig(BaseModel):
    variant: ScenarioVariant
    auth_gate: str = "THEORY_SAVE"  # JUST_IN_TIME, THEORY_SAVE, BEFORE_REVEAL
    deep_reframe_depth: str = "STANDARD"  # SHORT, STANDARD, DEEP_PROGRESSIVE_DISCLOSURE
    trust_label_style: str = "DETAILED"  # COMPACT, DETAILED
    layout_style: str = "STANDARD"  # EVIDENCE_FIRST, STANDARD, ANALYSIS_FIRST, COMMUNITY_AND_MAGAZINE_VISIBLE
    latency_level: str = "NORMAL"  # LOW, NORMAL, HIGH
    media_latency_level: str = "NORMAL"  # NORMAL, HIGH
    community_density: str = "NORMAL"  # LOW, NORMAL, HIGH
    verified_proof_count: int = 0
    rewatch_pattern_public_count: int = 0
    deep_reframe_empty_state: bool = True
    hypothetical_product_config: bool = False


class SimulationRunConfig(BaseModel):
    mode: SimulationMode = SimulationMode.CI
    unique_source_personas: int = 10000
    variants: List[ScenarioVariant] = Field(default_factory=lambda: [
        ScenarioVariant.QUICK_VALUE,
        ScenarioVariant.CURRENT_BASELINE,
        ScenarioVariant.EARLY_AUTH,
        ScenarioVariant.DEEP_ANALYSIS,
        ScenarioVariant.COMMUNITY_FIRST,
    ])
    replications: int = 1
    seed: int = 42
    policy_version: str = "reframe_us_audience_policy_v1"
    chunk_size: int = 10000
    allow_demographic_behavior_assumptions: bool = False
    include_traces_count: int = 100


class RepresentativeSessionTrace(BaseModel):
    session_id: str
    persona_id: str
    scenario_id: str
    replication_seed: int
    states_visited: List[str]
    transition_durations_sec: Dict[str, float]
    total_duration_sec: float
    dropoff_step: Optional[str] = None
    dropoff_reason: str
    deep_reframe_completed: bool = False
    rewatch_started: bool = False
    rewatch_completed: bool = False
    theory_started: bool = False
    theory_completed: bool = False
    post_created: bool = False
    comment_created: bool = False
    counterclaim_created: bool = False
    magazine_article_read: bool = False
    return_visit_reached: bool = False
    return_intent_score: float = 0.0


# ---------------------------------------------------------------------------
# Metrics & Intervals
# ---------------------------------------------------------------------------

class MetricDetail(BaseModel):
    metric_name: str
    numerator: int
    denominator: int
    rate: float


class SimulationInterval(BaseModel):
    metric_name: str
    point_estimate: float
    lower_bound: float
    upper_bound: float
    confidence_level: float = 0.95
    effective_unit: str = "SOURCE_PERSONA"  # SOURCE_PERSONA or REPLICATION_SEED
    interval_method: str = "POISSON_PERSONA_CLUSTER_BOOTSTRAP"
    cluster_sample_size: int = 0
    bootstrap_scheme: str = "POISSON_CLUSTER"
    bootstrap_replications: int = 500
    bootstrap_seed: int = 42
    label: str = "SIMULATION_INTERVAL"
    disclaimer: str = (
        "The interval describes variability under the configured synthetic behavior model "
        "and does not estimate sampling uncertainty among actual Reframe users."
    )


class FunnelMetrics(BaseModel):
    landing_to_film_hub_rate: float
    film_hub_to_reveal_rate: float
    film_hub_to_spoiler_gate_rate: float = 0.0
    spoiler_gate_to_reveal_rate: float = 0.0
    spoiler_gate_completion_rate: float
    reveal_to_deep_reframe_rate: float
    deep_reframe_entry_rate: float = 0.0
    deep_reframe_completion_rate: float = 0.0
    deep_reframe_read_rate: float = 0.0  # Alias for deep_reframe_entry_rate
    rewatch_start_rate: float
    rewatch_completion_rate: float = 0.0
    theory_start_rate: float
    theory_completion_rate: float
    community_read_rate: float
    community_contribution_rate: float
    comment_rate: float
    counterclaim_rate: float
    magazine_read_rate: float
    return_intent_proxy: float
    core_value_activation_rate: float = 0.0
    downstream_engagement_rate: float = 0.0
    creator_conversion_rate: float = 0.0
    full_golden_path_rate: float = 0.0
    golden_path_completion_rate: float
    time_to_first_value_sec: float
    p50_session_duration_sec: float
    p95_session_duration_sec: float
    moderation_candidate_rate: float
    error_abandonment_rate: float

    metric_details: Dict[str, MetricDetail] = Field(default_factory=dict)
    denominators: Dict[str, int]
    dropoff_counts_by_reason: Dict[str, int]
    state_entry_counts: Dict[str, int]
    simulation_intervals: Dict[str, SimulationInterval] = Field(default_factory=dict)



class CohortSummary(BaseModel):
    slice_dimension: str
    cohort_key: str
    session_count: int
    unweighted_share: float
    weighted_share: float
    golden_path_completion_rate: float
    deep_reframe_read_rate: float
    deep_reframe_entry_rate: float = 0.0
    deep_reframe_completion_rate: float = 0.0
    rewatch_start_rate: float
    rewatch_completion_rate: float = 0.0
    theory_completion_rate: float
    community_contribution_rate: float
    magazine_read_rate: float
    return_intent_proxy: float


class BottleneckItem(BaseModel):
    rank: int
    state: str
    primary_dropoff_reasons: List[str]
    affected_share: float
    affected_sessions: int
    sensitivity_score: float
    stability_score: float
    suggested_experiment: str
    limitations: str


class BottleneckReport(BaseModel):
    ranking_score_formula: str
    bottlenecks: List[BottleneckItem]


class SensitivityFactorResult(BaseModel):
    factor_name: str
    perturbation: str  # e.g., "+20%", "-20%"
    baseline_rate: float = 0.0
    perturbed_rate: float = 0.0
    delta: float = 0.0
    numerator: int = 0
    denominator: int = 0
    paired_seed: int = 42
    scenario_hash: str = ""
    perturbed_config_hash: str = ""
    golden_path_delta: float
    rewatch_delta: float
    theory_delta: float
    community_delta: float
    magazine_delta: float
    return_intent_delta: float


class SensitivityReport(BaseModel):
    factors_tested: List[str]
    perturbation_percentage: float = 20.0
    sample_size: int = 10000
    paired_scenario: str = "CURRENT_BASELINE"
    results: List[SensitivityFactorResult]
    dominant_assumptions: List[str]


class DirectionalDemandInput(BaseModel):
    simulation_run_id: Optional[uuid.UUID] = None
    forecast_class: str = "ASSUMPTION_BASED_DIRECTIONAL"
    monthly_visitors: int = 50000
    traffic_source_mix: Dict[str, float] = Field(
        default_factory=lambda: {"organic_search": 0.40, "social": 0.30, "direct": 0.20, "referral": 0.10}
    )
    returning_visitor_rate: float = 0.25
    catalog_size: int = 1
    new_article_frequency_monthly: int = 10
    new_community_post_frequency_monthly: int = 50
    campaign_conversion_assumption: float = 0.05
    real_user_forecast: bool = False


class DirectionalDemandResult(BaseModel):
    forecast_class: str = "ASSUMPTION_BASED_DIRECTIONAL"
    real_user_forecast: bool = False
    source_run_id: Optional[str] = None
    source_policy_version: str = "reframe_us_audience_policy_v1"
    source_scenario: str = "CURRENT_BASELINE"
    disclaimer: str = (
        "This directional demand scenario is strictly assumption-based and derived from external visitor assumptions "
        "combined with synthetic behavior conversion rates. It is not an empirical real-user forecast or market validation."
    )
    monthly_visitors: int
    monthly_golden_path_completions: Dict[str, int]  # min, expected, max
    monthly_rewatch_sessions: Dict[str, int]
    monthly_theories_created: Dict[str, int]
    monthly_community_contributions: Dict[str, int]
    monthly_magazine_reads: Dict[str, int]
    expected_synthetic_moderation_workload_items: Dict[str, int]
    request_volume_monthly: Dict[str, int]


# ---------------------------------------------------------------------------
# Full Simulation Run Result
# ---------------------------------------------------------------------------

class SimulationRunResult(BaseModel):
    disclaimer: str = (
        "SYNTHETIC SIMULATION DISCLAIMER: Results are generated from a deterministic simulation of synthetic viewer personas "
        "derived from nvidia/Nemotron-Personas-USA under explicit behavior policy assumptions. "
        "They do NOT constitute empirical real-user demand, market validation, or product-market fit."
    )
    dataset_id: str = "nvidia/Nemotron-Personas-USA"
    dataset_revision: str = "5b4cd35ab46490c1da1bd2b5a2324d6f871be180"
    dataset_license: str = "CC BY 4.0"
    source_mode: str = "REPRO_SAMPLE"
    source_cache_sha256: str = ""
    source_cache_manifest_sha256: str = ""
    sample_method: str = "FULL_SOURCE_HASH_PRIORITY_RESERVOIR_V2"
    source_rows_seen: int = 1000000
    eligible_adult_rows: int = 783005
    full_stream_completed: bool = True
    policy_version: str = "reframe_us_audience_policy_v1"
    policy_hash: str = "deterministic_behavior_policy_v1"
    scenario_hash: str = "scenario_matrix_v1"
    simulation_mode: SimulationMode
    unique_source_personas: int
    synthetic_sessions: int
    scenario_count: int
    replication_count: int
    interval_method: str = "POISSON_PERSONA_CLUSTER_BOOTSTRAP"
    cluster_sample_size: int = 10000
    bootstrap_replications: int = 500
    bootstrap_seed: int = 42
    sensitivity_sample_size: int = 10000
    seed: int
    runtime_seconds: float
    peak_memory_mb: float
    sessions_per_second: float
    source_records_per_second: float
    termination_reason: TerminationReason
    convergence_status: bool
    convergence_history: List[Dict[str, Any]] = Field(default_factory=list)

    scenario_metrics: Dict[str, FunnelMetrics] = Field(default_factory=dict)
    aggregate_funnel: FunnelMetrics
    balanced_eval_cohorts: List[CohortSummary] = Field(default_factory=list)
    source_weighted_cohorts: List[CohortSummary] = Field(default_factory=list)
    bottlenecks: BottleneckReport
    sensitivity: SensitivityReport
    directional_demand: DirectionalDemandResult
    load_profile_location: str = "data/simulation/load/usa_audience_request_mix_v1.json"
    representative_traces: List[RepresentativeSessionTrace] = Field(default_factory=list)
    zero_model_disclosure: str = "ZERO_GENERATIVE_MODEL_CALLS_CONFIRMED"
    paid_model_calls: int = 0
    live_model_used: bool = False
