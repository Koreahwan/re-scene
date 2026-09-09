EVIDENCE_VERIFIER_SYSTEM_INSTRUCTION = """
You are the Evidence Verifier for Reframe.
Your role is to rigorously evaluate whether an earlier scene's narrative meaning was fundamentally reframed by a later Reveal.

Strict Rules:
1. Grounding: All claims about changes in meaning MUST cite concrete observable event or fact IDs provided in the context.
2. Character Intent: Never invent or assume secret intentions unless explicitly evidenced by prior facts/events or the revealed truth.
3. Allowed Relations:
   - DIRECT_FORESHADOWING: An explicit clue or setup directly pointing to the reveal.
   - REINTERPRETATION: An action or dialogue that appeared normal/innocent earlier but gains an entirely new meaning given the reveal.
   - CHARACTER_MOTIVATION: A character's earlier unexplained or misleading behavior is now explained by their true identity/motive.
   - CONTRADICTION: An earlier statement or alibi is proven to be a deliberate lie.
   - COINCIDENCE: The scene features the entity but has no causal or narrative connection to the reveal.
   - IRRELEVANT: The scene has no narrative bearing on the reveal.
4. If a scene is merely COINCIDENCE or IRRELEVANT, classify it accordingly.
5. If evidence is ambiguous or unsupported, set `is_supported` to false and list `unsupported_claims`.
""".strip()


def build_verification_prompt(
    reveal_title: str,
    previous_belief: str,
    revealed_fact: str,
    scene_summary: str,
    dialogue_summary: str,
    events_text: str,
    facts_text: str,
) -> str:
    return f"""
EVALUATE THIS SCENE AGAINST THE REVEAL:

[REVEAL]
Title: {reveal_title}
Previous Audience Belief: {previous_belief}
Revealed True Fact: {revealed_fact}

[PRIOR SCENE]
Summary: {scene_summary}
Dialogue: {dialogue_summary}

[OBSERVABLE EVENTS]
{events_text}

[OBSERVABLE FACTS]
{facts_text}

Respond in strict JSON with the following structure:
{{
  "relation_type": "REINTERPRETATION",
  "before_meaning": "What the audience thought was happening before the reveal.",
  "after_meaning": "What was actually happening given the reveal.",
  "evidence_event_ids": ["ev-1", "ev-2"],
  "evidence_fact_ids": ["fact-1"],
  "confidence": 0.95,
  "is_supported": true,
  "unsupported_claims": []
}}
""".strip()
