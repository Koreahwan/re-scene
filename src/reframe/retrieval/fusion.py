from typing import Dict, List
from reframe.domain.models import ReframeCandidate


def reciprocal_rank_fusion(
    ranked_lists: Dict[str, List[ReframeCandidate]],
    k: int = 60,
    max_candidates: int = 30,
) -> List[ReframeCandidate]:
    """
    Combines ranked candidate lists from multiple retrieval channels (e.g. entity, event, lexical)
    using standard Reciprocal Rank Fusion (RRF):
        RRF_Score(d) = sum_{source} 1.0 / (k + rank_in_source)
    """
    scores: Dict[str, float] = {}
    candidate_map: Dict[str, ReframeCandidate] = {}
    reasons_map: Dict[str, List[str]] = {}

    for source_name, candidate_list in ranked_lists.items():
        for rank, cand in enumerate(candidate_list, start=1):
            sid = cand.scene_id
            if sid not in candidate_map:
                candidate_map[sid] = cand.model_copy()
                reasons_map[sid] = []

            rrf_delta = 1.0 / (k + rank)
            scores[sid] = scores.get(sid, 0.0) + rrf_delta
            reasons_map[sid].append(f"{source_name}#rank_{rank}(+{rrf_delta:.4f})")

            # Track rank attribution
            if source_name == "entity":
                candidate_map[sid].entity_rank = rank
            elif source_name == "lexical":
                candidate_map[sid].lexical_rank = rank
            elif source_name == "semantic":
                candidate_map[sid].semantic_rank = rank

    # Sort descending by RRF score
    sorted_sids = sorted(scores.keys(), key=lambda sid: scores[sid], reverse=True)

    result: List[ReframeCandidate] = []
    for sid in sorted_sids[:max_candidates]:
        cand = candidate_map[sid]
        cand.rrf_score = scores[sid]
        cand.retrieval_reasons = reasons_map[sid]
        result.append(cand)

    return result
