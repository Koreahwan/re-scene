"""
Unit Tests for Standard IR Evaluation Math (Recall@k, Precision@k, MRR)
Zero Paid Model Calls.
"""
from reframe.domain.models import ReframeResult, ReframedMomentCard
from reframe.domain.enums import ReframeRunStatus, RelationType
from src.reframe.evals.evaluator import GoldenDatasetEvaluator


def test_standard_precision_recall_mrr_formulas():
    # 4 ground truth positives
    positives = ["scene-tbw-c011", "scene-tbw-c017", "scene-tbw-c021", "scene-tbw-c028"]
    cutoff_ms = 4860000

    cards = [
        ReframedMomentCard(
            moment_id="m1",
            scene_id="scene-tbw-c001",
            start_ms=1000,
            end_ms=2000,
            title="Card 1",
            location="Oakdale Manor Hallway",
            scene_summary="Scene 1 summary",
            relation_type=RelationType.DIRECT_FORESHADOWING,
            before_meaning="Before 1",
            after_meaning="After 1",
            clue_description="Clue 1"
        ),
        ReframedMomentCard(
            moment_id="m2",
            scene_id="scene-tbw-c011",
            start_ms=2000,
            end_ms=3000,
            title="Card 2",
            location="Private Study",
            scene_summary="Scene 11 summary",
            relation_type=RelationType.REINTERPRETATION,
            before_meaning="Before 2",
            after_meaning="After 2",
            clue_description="Clue 2"
        ),
        ReframedMomentCard(
            moment_id="m3",
            scene_id="scene-tbw-c017",
            start_ms=3000,
            end_ms=4000,
            title="Card 3",
            location="Grand Fireplace",
            scene_summary="Scene 17 summary",
            relation_type=RelationType.CONTRADICTION,
            before_meaning="Before 3",
            after_meaning="After 3",
            clue_description="Clue 3"
        ),
        ReframedMomentCard(
            moment_id="m4",
            scene_id="scene-tbw-c002",
            start_ms=4000,
            end_ms=5000,
            title="Card 4",
            location="Library",
            scene_summary="Scene 2 summary",
            relation_type=RelationType.DIRECT_FORESHADOWING,
            before_meaning="Before 4",
            after_meaning="After 4",
            clue_description="Clue 4"
        ),
        ReframedMomentCard(
            moment_id="m5",
            scene_id="scene-tbw-c003",
            start_ms=5000,
            end_ms=6000,
            title="Card 5",
            location="Staircase",
            scene_summary="Scene 3 summary",
            relation_type=RelationType.CHARACTER_MOTIVATION,
            before_meaning="Before 5",
            after_meaning="After 5",
            clue_description="Clue 5"
        ),
    ]

    res = ReframeResult(
        run_id="run-eval-test-01",
        movie_id="the-bat-whispers-1930",
        reveal_id="reveal-anderson-identity",
        spoiler_cutoff_ms=cutoff_ms,
        status=ReframeRunStatus.COMPLETED,
        cards=cards
    )

    eval_result = GoldenDatasetEvaluator.evaluate_run(
        result=res,
        positive_scene_ids=positives,
        hard_negative_scene_ids=[],
        poison_pill_future_ids=[],
        spoiler_cutoff_ms=cutoff_ms
    )

    # TP in top-5 = 2 (scenes 11 and 17)
    # Total retrieved = 5 -> Precision@5 = 2/5 = 0.40
    # Total positives = 4 -> Recall@5 = 2/4 = 0.50
    # First TP is at index 1 (rank 2) -> MRR = 1/2 = 0.50
    assert eval_result["precision"] == 0.40
    assert eval_result["recall"] == 0.50
    assert eval_result["reciprocal_rank"] == 0.50
    assert eval_result["is_valid"] is True


def test_empty_retrieval_returns_zero_scores():
    positives = ["scene-tbw-c011", "scene-tbw-c017"]
    res = ReframeResult(
        run_id="run-empty",
        movie_id="the-bat-whispers-1930",
        reveal_id="reveal-anderson-identity",
        spoiler_cutoff_ms=4860000,
        status=ReframeRunStatus.COMPLETED,
        cards=[]
    )
    eval_result = GoldenDatasetEvaluator.evaluate_run(
        result=res,
        positive_scene_ids=positives,
        hard_negative_scene_ids=[],
        poison_pill_future_ids=[],
        spoiler_cutoff_ms=4860000
    )
    assert eval_result["precision"] == 0.0
    assert eval_result["recall"] == 0.0
    assert eval_result["reciprocal_rank"] == 0.0
