"""
Reframe V7 Synthetic Content Factory
Contains curated static anchor assets strictly grounded in The Bat Whispers (1930) canonical V3 evidence.
Zero External Generative Model Calls.
Zero hallucinated IDs, facts, or timestamps.
Strict Compliance with Canon: Grounded in observed V3 evidence with zero unsupported director intent or causal certainty.
"""
from __future__ import annotations
import hashlib
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# 20 Curated Topics strictly matched with Canonical V3 Evidence
# ---------------------------------------------------------------------------

ARTICLE_TOPICS = [
    # 1. Scene 1
    ("Opening Credits & Adaptation Provenance", "SCENE_BREAKDOWN", "scene-tbw-c001", "fact-c001-01", 15000, "ev-c001-01", 15000, 0, "reveal-anderson-identity",
     "Examination of opening title cards establishing the adaptation from Mary Roberts Rinehart and Avery Hopwood's stage play.",
     "The opening title credits display cast and source play provenance at 15000ms."),
    # 2. Scene 2
    ("Police Dispatch & City Traversal", "SCENE_BREAKDOWN", "scene-tbw-c002", "fact-c002-01", 120000, "ev-c002-01", 120000, 120000, "reveal-anderson-identity",
     "Tracking the police cruiser departing headquarters and traveling across city streets at night.",
     "A police vehicle departs Police Headquarters and navigates dark streets at 120000ms."),
    # 3. Scene 3
    ("Threat Letter Delivered to Bell Library", "EVIDENCE_ROUNDUP", "scene-tbw-c003", "fact-c003-01", 255000, "ev-c003-01", 240000, 240000, "reveal-anderson-identity",
     "Forensic breakdown of the threat letter delivered to John Bell's study signed by 'The Bat'.",
     "Mr. Bell reads a threatening note signed by 'The Bat' in his library while police wait at 240000ms."),
    # 4. Scene 4
    ("Man Leaning Out Window and Hidden Wall Safe", "SCENE_BREAKDOWN", "scene-tbw-c004", "fact-c004-01", 420000, "ev-c004-01", 375000, 360000, "reveal-masked-robbery-vault",
     "Examining the man leaning through the window holding a cord and the butler revealing the wall safe behind draperies.",
     "A man in a dark suit leans out an open window holding a cord at 375000ms; the butler opens a wall safe behind curtains at 420000ms."),
    # 5. Scene 5
    ("Elevated Perspective on Bank Vault Door", "FILM_FORM_ESSAY", "scene-tbw-c005", "fact-c005-01", 480000, "ev-c005-01", 480000, 480000, "reveal-masked-robbery-vault",
     "Analysis of the elevated camera viewpoint overlooking the circular bank vault door.",
     "A bank vault room is observed from an elevated viewpoint while a worker operates near the vault door at 480000ms."),
    # 6. Scene 6
    ("Fleming Estate Gate & Exterior Grounds", "REWATCH_GUIDE", "scene-tbw-c006", "fact-c006-01", 600000, "ev-c006-01", 630000, 600000, "reveal-secret-room-location",
     "Tracking the exterior entrance to the Fleming estate and a man carrying a bag walking across the grounds.",
     "The estate gate pillars bear the inscription FLEMING at 600000ms; a man walks across exterior grounds carrying a bag at 630000ms."),
    # 7. Scene 7
    ("Anxious Exchange in Great Hall", "SCENE_BREAKDOWN", "scene-tbw-c007", "fact-c007-01", 720000, "ev-c007-01", 720000, 720000, "reveal-anderson-identity",
     "Lizzie Allen expresses distress while speaking with Miss Cornelia in the Oakdale Great Hall.",
     "Lizzie Allen interacts anxiously with Miss Cornelia Van Gorder in Oakdale Manor at 720000ms."),
    # 8. Scene 8
    ("Ouija Board Interaction & Basement Inspection", "EVIDENCE_ROUNDUP", "scene-tbw-c008", "fact-c008-02", 885000, "ev-c008-01", 840000, 840000, "reveal-secret-room-location",
     "Cornelia and Lizzie consult a Ouija board before investigating activity in the basement.",
     "Cornelia and Lizzie operate a planchette over a Ouija board at 840000ms; the basement contains a wooden ladder and boiler at 885000ms."),
    # 9. Scene 9
    ("Bat Silhouette Projection & Robbery Headline", "FILM_FORM_ESSAY", "scene-tbw-c009", "fact-c009-01", 1050000, "ev-c009-01", 960000, 960000, "reveal-anderson-identity",
     "Examining the bat silhouette cast against the exterior wall and the bank robbery newspaper headline.",
     "A bat silhouette appears cast against the exterior wall at 960000ms; a newspaper displays headline BANK ROBBED at 1050000ms."),
    # 10. Scene 10
    ("Interior Staircase Observation & Caretaker Exchange", "REWATCH_GUIDE", "scene-tbw-c010", "fact-c010-01", 1080000, "ev-c010-01", 1125000, 1080000, "reveal-secret-room-location",
     "Cornelia and Lizzie view the staircase before conversing with caretaker Billy.",
     "The interior staircase is observed from a doorway at 1080000ms; caretaker Billy speaks in an agitated manner at 1125000ms."),
    # 11. Scene 11
    ("Garage Visit & Great Hall Discussion During Storm", "SCENE_BREAKDOWN", "scene-tbw-c011", "fact-c011-01", 1260000, "ev-c011-01", 1200000, 1200000, "reveal-brooks-innocence",
     "Dale visits the estate garage before returning to discuss occurrences during a lightning storm.",
     "Cornelia walks toward the window as Lizzie reacts fearfully at 1200000ms; sky displays lightning flashes at 1260000ms."),
    # 12. Scene 12
    ("Perimeter Silhouettes & Billy Peeking Through Doorway", "FILM_FORM_ESSAY", "scene-tbw-c012", "fact-c012-01", 1350000, "ev-c012-01", 1350000, 1320000, "reveal-anderson-identity",
     "Caretaker Billy observes occupants conversing in the Great Hall while Cornelia knits.",
     "Cornelia knits in the Great Hall at 1350000ms while caretaker Billy cautiously peeks through the doorway."),
    # 13. Scene 13
    ("Note Attached to Umbrella & Dr. Wells Entry", "REWATCH_GUIDE", "scene-tbw-c013", "fact-c013-01", 1440000, "ev-c013-01", 1440000, 1440000, "reveal-secret-room-location",
     "Cornelia and Lizzie discover a note attached to an umbrella before Dr. Wells enters the Great Hall.",
     "In Oakdale Manor Great Hall, Cornelia knits, a note is found attached to an umbrella, and Dr. Wells enters wearing an overcoat at 1440000ms."),
    # 14. Scene 14
    ("Dr. Wells Conference & Table Discussion", "SCENE_BREAKDOWN", "scene-tbw-c014", "fact-c014-02", 1560000, "ev-c014-01", 1560000, 1560000, "reveal-anderson-identity",
     "Dr. Wells confers with Cornelia before departing; a telephone is operated near the staircase.",
     "Dr. Wells holds his hat while speaking to Miss Cornelia wearing a lace shawl in the hall at 1560000ms."),
    # 15. Scene 15
    ("Doctor Wells Exit & Doorway Observation", "EVIDENCE_ROUNDUP", "scene-tbw-c015", "fact-c015-01", 1680000, "ev-c015-01", 1680000, 1680000, "reveal-brooks-innocence",
     "Cornelia and a man converse at a table; Doctor Wells interacts with items on a desk and exits.",
     "Cornelia is seated at the table opposite a man in a suit at 1680000ms while Doctor Wells exits through double doors."),
    # 16. Scene 16
    ("Octagonal Table Discussion & Hallway Meeting", "SCENE_BREAKDOWN", "scene-tbw-c016", "fact-c016-01", 1800000, "ev-c016-01", 1800000, 1800000, "reveal-secret-room-location",
     "Cornelia converses at an octagonal table with hat and gloves placed between them.",
     "Cornelia sits at the octagonal table conversing with a man in a dark suit at 1800000ms with hat and gloves on table."),
    # 17. Scene 17
    ("Detective Anderson Interviews Cornelia with Notepad", "TRUST_LABEL_EXPLAINER", "scene-tbw-c017", "fact-c017-01", 1920000, "ev-c017-01", 1920000, 1920000, "reveal-anderson-identity",
     "Detective Anderson interviews Cornelia and Lizzie while writing in his notepad as lights dim.",
     "Detective Anderson holds a notepad and pencil while questioning Cornelia in the hall at 1920000ms."),
    # 18. Scene 18
    ("Occupants Moving Across Staircase Entry", "SCENE_BREAKDOWN", "scene-tbw-c018", "fact-c018-02", 2100000, "ev-c018-01", 2040000, 2040000, "reveal-secret-room-location",
     "A young woman runs past the staircase entry while a man in a suit is on the Great Hall staircase.",
     "A young woman runs past the staircase entry at 2040000ms; a man in a suit is on the staircase at 2100000ms."),
    # 19. Scene 19
    ("Detective Anderson in Trench Coat & Basement Laundry Incident", "SCENE_BREAKDOWN", "scene-tbw-c019", "fact-c019-01", 2190000, "ev-c019-01", 2175000, 2160000, "reveal-anderson-identity",
     "Detective Anderson stands in the hall with Dale while movements occur in upper corridors.",
     "Dale walks across the main hall at 2175000ms; Detective Anderson wears a trench coat and hat at 2190000ms."),
    # 20. Scene 20
    ("Bookcase Inspection with Rolled Paper", "EVIDENCE_ROUNDUP", "scene-tbw-c020", "fact-c020-02", 2280000, "ev-c020-01", 2280000, 2280000, "reveal-secret-room-location",
     "Dale converses with a man in an overcoat inspecting a bookcase with a rolled paper inside Oakdale Manor.",
     "Dale sits in an armchair talking with a man in an overcoat inspecting a bookcase at 2280000ms."),
]


def generate_curated_articles() -> List[Dict[str, Any]]:
    articles = []
    for idx, (title, art_type, scene_id, fact_id, fact_ts, ev_id, ev_ts, scene_start_ts, rev_id, dek, factual_summary) in enumerate(ARTICLE_TOPICS, start=1):
        articles.append({
            "stable_key": f"mag_art_{idx:03d}_{scene_id.replace('-', '_')}",
            "title": f"{idx:02d}. {title}",
            "article_type": art_type,
            "dek": dek,
            "spoiler_cutoff_ms": 4860000,
            "tagged_reveal_ids": [rev_id],
            "evidence_refs": [
                {
                    "evidence_type": "FACT",
                    "evidence_id": fact_id,
                    "scene_id": scene_id,
                    "timestamp_ms": fact_ts,
                    "trust_class": "OBSERVED_EVIDENCE",
                },
                {
                    "evidence_type": "EVENT",
                    "evidence_id": ev_id,
                    "scene_id": scene_id,
                    "timestamp_ms": ev_ts,
                    "trust_class": "OBSERVED_EVIDENCE",
                },
                {
                    "evidence_type": "SCENE",
                    "evidence_id": scene_id,
                    "scene_id": scene_id,
                    "timestamp_ms": scene_start_ts,
                    "trust_class": "CANONICAL_FACT",
                }
            ],
            "body_sections": {
                "WHAT_THE_FILM_SHOWS": f"At {fact_ts//60000:02d}:{(fact_ts%60000)//1000:02d} in {scene_id}, canonical footage records: {factual_summary}",
                "CANONICAL_METADATA": f"Work: The Bat Whispers (1930). Scene: {scene_id} ({scene_start_ts}ms). Verified Evidence: {fact_id} ({fact_ts}ms), {ev_id} ({ev_ts}ms).",
                "ENGINE_INTERPRETATION": f"The narrative memory graph links observable evidence in {scene_id} with downstream structural reveal {rev_id} under an ENGINE_INFERENCE trust label.",
                "SYNTHETIC_AUTHOR_VIEW": "As an analytical viewer examining structural mystery framing, this moment anchors critical rewatch value.",
                "ALTERNATIVE_EXPLANATION": "A conventional genre trope intended for atmospheric misdirection rather than direct plot causality.",
                "REWATCH_TIMESTAMPS": f"{fact_ts//60000:02d}:{(fact_ts%60000)//1000:02d} (Scene {scene_id} focal point)."
            }
        })
    return articles


CURATED_MAGAZINE_ARTICLES: List[Dict[str, Any]] = generate_curated_articles()


def generate_curated_posts() -> List[Dict[str, Any]]:
    posts = []
    for idx, (title, _, scene_id, fact_id, fact_ts, ev_id, ev_ts, scene_start_ts, rev_id, dek, factual_summary) in enumerate(ARTICLE_TOPICS, start=1):
        posts.append({
            "stable_key": f"comm_post_{idx:03d}_{scene_id.replace('-', '_')}",
            "title": f"Observational Note #{idx:02d}: {title} ({scene_id})",
            "body": f"Reviewing {scene_id}. Canonical footage at {fact_ts}ms documents {factual_summary}. COMMUNITY_INTERPRETATION: This observation may relate to {rev_id}.",
            "post_type": "THEORY_DISCUSSION",
            "spoiler_cutoff_ms": 4860000,
            "tagged_reveal_ids": [rev_id],
            "trust_class": "COMMUNITY_INTERPRETATION",
            "cited_evidence": [fact_id, ev_id],
            "evidence_refs": [
                {
                    "evidence_type": "FACT",
                    "evidence_id": fact_id,
                    "scene_id": scene_id,
                    "timestamp_ms": fact_ts,
                    "trust_class": "OBSERVED_EVIDENCE",
                },
                {
                    "evidence_type": "EVENT",
                    "evidence_id": ev_id,
                    "scene_id": scene_id,
                    "timestamp_ms": ev_ts,
                    "trust_class": "OBSERVED_EVIDENCE",
                }
            ],
            "sample_comments": [
                f"Noticed {fact_id} in {scene_id}. On first viewing this appeared as background setting.",
                f"Rewatching at {fact_ts}ms highlights the recorded physical blocking in {ev_id}."
            ]
        })
    return posts


CURATED_COMMUNITY_POSTS: List[Dict[str, Any]] = generate_curated_posts()


def generate_curated_counterclaims() -> List[Dict[str, Any]]:
    counterclaims = []
    for idx, (title, _, scene_id, fact_id, fact_ts, ev_id, ev_ts, scene_start_ts, rev_id, _, factual_summary) in enumerate(ARTICLE_TOPICS, start=1):
        counterclaims.append({
            "stable_key": f"comm_claim_{idx:03d}_{scene_id.replace('-', '_')}",
            "title": f"Alternative Hypothesis for {scene_id}: Staging Ambiguity",
            "body": f"While initial interpretations connect {fact_id} at {fact_ts}ms to {rev_id}, the physical blocking in {ev_id} ({ev_ts}ms) permits an alternative interpretation: genre atmosphere rather than direct causal evidence.",
            "challenged_premise": f"Causal link in {scene_id} for {fact_id}",
            "alternative_explanation": f"Theatrical staging convention in {scene_id}",
            "spoiler_cutoff_ms": 4860000,
            "tagged_reveal_ids": [rev_id],
            "trust_class": "COMMUNITY_INTERPRETATION",
            "cited_evidence": [fact_id, ev_id],
            "evidence_refs": [
                {
                    "evidence_type": "FACT",
                    "evidence_id": fact_id,
                    "scene_id": scene_id,
                    "timestamp_ms": fact_ts,
                    "trust_class": "COMMUNITY_INTERPRETATION",
                },
                {
                    "evidence_type": "EVENT",
                    "evidence_id": ev_id,
                    "scene_id": scene_id,
                    "timestamp_ms": ev_ts,
                    "trust_class": "COMMUNITY_INTERPRETATION",
                }
            ]
        })
    return counterclaims


CURATED_COUNTERCLAIMS: List[Dict[str, Any]] = generate_curated_counterclaims()
