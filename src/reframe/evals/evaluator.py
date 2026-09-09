from typing import List, Dict, Set, Any
from dataclasses import dataclass
from reframe.domain.models import ReframeResult, ReframedMomentCard
from reframe.domain.enums import ReframeRunStatus


@dataclass
class EvaluationMetrics:
    total_eval_cases: int
    mean_recall_at_k: float
    mean_precision_at_k: float
    mean_reciprocal_rank: float
    future_leakage_rate: float
    presentation_purity_rate: float
    pass_all_invariants: bool
    details: List[Dict[str, Any]]


class GoldenDatasetEvaluator:
    """
    Evaluates Reframe retrieval & verification results against Golden dataset annotations.
    """

    def __init__(self, golden_data: Dict[str, Any]):
        self.golden = golden_data

    @staticmethod
    def evaluate_run(
        result: ReframeResult,
        positive_scene_ids: List[str],
        hard_negative_scene_ids: List[str],
        poison_pill_future_ids: List[str],
        spoiler_cutoff_ms: int,
    ) -> Dict[str, Any]:
        def _norm(s: str) -> str:
            return s.replace("scene-tbw-c", "scene-tbw-").replace("scene-tbw-", "").lstrip("0") or "0"

        retrieved_ids = [c.scene_id for c in result.cards]
        retrieved_norms = [_norm(c.scene_id) for c in result.cards]
        pos_norm = {_norm(s) for s in positive_scene_ids}
        neg_norm = {_norm(s) for s in hard_negative_scene_ids}
        poison_norm = {_norm(s) for s in poison_pill_future_ids}

        # Invariant 1: Future Leakage Check
        future_leakage_count = 0
        for card in result.cards:
            if card.start_ms >= spoiler_cutoff_ms or _norm(card.scene_id) in poison_norm:
                future_leakage_count += 1

        # Invariant 2: Presentation Purity Check (No COINCIDENCE / IRRELEVANT)
        unpresentable_count = sum(1 for c in result.cards if not c.relation_type.is_user_presentable)

        # Compute Grounded Precision & Recall using standard IR formulas (Freeze Spec 08 / Section 19)
        top_k = 5
        top_retrieved_norms = retrieved_norms[:top_k]
        top_retrieved_ids = retrieved_ids[:top_k]

        if result.status == ReframeRunStatus.COMPLETED:
            if pos_norm:
                true_positives = [sid for sid, norm in zip(top_retrieved_ids, top_retrieved_norms) if norm in pos_norm]
                # Precision@5 = TP@5 / returned_count_at_5
                precision = len(true_positives) / len(top_retrieved_ids) if top_retrieved_ids else 0.0
                # Recall@5 = TP@5 / total_ground_truth_positives
                recall = len(true_positives) / len(pos_norm) if pos_norm else 0.0
                # MRR = 1 / rank of first relevant item in retrieved list
                first_tp_idx = next((i for i, norm in enumerate(retrieved_norms) if norm in pos_norm), None)
                rr = (1.0 / (first_tp_idx + 1)) if first_tp_idx is not None else 0.0
            else:
                recall = 0.0
                precision = 0.0
                rr = 0.0

        else:
            # If ABSTAINED was expected (pos_norm is empty):
            if not pos_norm:
                recall = 1.0
                precision = 1.0
                rr = 1.0
            else:
                # Abstaining when ground truth positives existed yields 0 recall
                recall = 0.0
                precision = 0.0
                rr = 0.0

        return {
            "run_id": result.run_id,
            "reveal_id": result.reveal_id,
            "status": result.status.value,
            "total_cards": len(result.cards),
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "reciprocal_rank": round(rr, 4),
            "future_leakage_count": future_leakage_count,
            "unpresentable_count": unpresentable_count,
            "is_valid": (future_leakage_count == 0 and unpresentable_count == 0),
        }

    def evaluate_all(self, results_by_reveal_id: Dict[str, ReframeResult]) -> Dict[str, Any]:
        eval_suite = self.golden.get("golden_eval_suite", {})
        run_summaries = []

        for rev_id, result in results_by_reveal_id.items():
            suite_case = eval_suite.get(rev_id, {})
            pos_ids = suite_case.get("positives", suite_case.get("positive_scene_ids", []))
            neg_ids = suite_case.get("hard_negatives", suite_case.get("hard_negative_scene_ids", []))
            poison_ids = suite_case.get("poison_pills", suite_case.get("poison_pill_future_scene_ids", []))

            run_summary = self.evaluate_run(
                result=result,
                positive_scene_ids=pos_ids,
                hard_negative_scene_ids=neg_ids,
                poison_pill_future_ids=poison_ids,
                spoiler_cutoff_ms=result.spoiler_cutoff_ms,
            )
            run_summaries.append(run_summary)

        n = len(run_summaries) if run_summaries else 1
        mean_recall = sum(r["recall"] for r in run_summaries) / n
        mean_precision = sum(r["precision"] for r in run_summaries) / n
        mean_mrr = sum(r["reciprocal_rank"] for r in run_summaries) / n
        total_future_leaks = sum(r["future_leakage_count"] for r in run_summaries)
        total_unpresentable = sum(r["unpresentable_count"] for r in run_summaries)

        return {
            "total_cases": len(run_summaries),
            "mean_recall_at_k": round(mean_recall, 4),
            "mean_precision_at_k": round(mean_precision, 4),
            "mean_reciprocal_rank": round(mean_mrr, 4),
            "future_leakage_rate": round(total_future_leaks / n, 4),
            "presentation_purity_rate": 1.0 if total_unpresentable == 0 else 0.0,
            "pass_all_invariants": (total_future_leaks == 0 and total_unpresentable == 0),
            "runs": run_summaries,
        }
