from reframe.domain.models import ReframeCandidate
from reframe.retrieval.fusion import reciprocal_rank_fusion


def test_reciprocal_rank_fusion_scoring_and_ranking():
    cand_a = ReframeCandidate(
        reveal_id="rev-1",
        scene_id="scene-A",
        movie_id="tbw-1930",
        start_ms=1000,
        summary="A",
    )
    cand_b = ReframeCandidate(
        reveal_id="rev-1",
        scene_id="scene-B",
        movie_id="tbw-1930",
        start_ms=2000,
        summary="B",
    )
    cand_c = ReframeCandidate(
        reveal_id="rev-1",
        scene_id="scene-C",
        movie_id="tbw-1930",
        start_ms=3000,
        summary="C",
    )

    # entity rank: [A (rank 1), B (rank 2)]
    # lexical rank: [A (rank 1), C (rank 2)]
    ranked_lists = {
        "entity": [cand_a, cand_b],
        "lexical": [cand_a, cand_c],
    }

    fused = reciprocal_rank_fusion(ranked_lists, k=60)

    # cand_a is rank 1 in both: 1/61 + 1/61 = 2/61 ≈ 0.03278
    # cand_b is rank 2 in entity only: 1/62 ≈ 0.01612
    # cand_c is rank 2 in lexical only: 1/62 ≈ 0.01612
    assert len(fused) == 3
    assert fused[0].scene_id == "scene-A"
    assert round(fused[0].rrf_score, 4) == round(2.0 / 61.0, 4)
    assert fused[0].entity_rank == 1
    assert fused[0].lexical_rank == 1
    assert len(fused[0].retrieval_reasons) == 2
