/**
 * Reframe V7 Pure Proof Detail View-Model Mapper
 * Strictly validates responses from GET /api/v1/proofs/{proof_id}.
 * 
 * Epistemic & Security Invariants:
 * - Discriminated view-model: EMPTY, ERROR, PROTECTED, VISIBLE.
 * - { data: null } is strictly honest EMPTY; missing data/non-object/mismatched ID is ERROR.
 * - Only visibility === 'VISIBLE' && !is_locked reads raw title, explanations, and premises.
 * - LOCKED / MASKED / UNKNOWN / missing visibility / VISIBLE + is_locked are PROTECTED.
 * - Protected states ONLY read safe_preview (title/summary); raw title/explanations/scene/time/evidence
 *   are NEVER read, fallen back to, or stored in the view model.
 * - Zero model promotions: ENGINE_INFERENCE is never promoted to VERIFIED_CANON.
 * Zero Paid Model Calls.
 */

export interface ObservedPremiseViewModel {
  key: string;
  eventId: string | null;
  sceneId: string | null;
  timestampMs: number | null;
  timestampFormatted: string | null;
  text: string;
  frameUrl: string | null;
}

export interface VisibleProofViewModel {
  kind: 'VISIBLE';
  proofId: string;
  workId: string | null;
  title: string;
  blindExplanation: string | null;
  revealExplanation: string | null;
  proofType: string | null;
  verificationStatus: string | null;
  trustNamespace: string | null;
  trustLabel: string | null;
  humanReviewStatus: string | null;
  observedPremises: ObservedPremiseViewModel[];
  alternativeExplanations?: string[];
}

export interface ProtectedProofViewModel {
  kind: 'PROTECTED';
  proofId: string;
  workId: string | null;
  visibility: string;
  isLocked: boolean;
  safeTitle: string;
  safeSummary: string;
  proofType: string | null;
  isUnderReview?: boolean;
}

export type ProofDetailResult =
  | { kind: 'EMPTY' }
  | { kind: 'ERROR'; error: string }
  | { kind: 'PROTECTED'; proof: ProtectedProofViewModel }
  | { kind: 'VISIBLE'; proof: VisibleProofViewModel };

const DEFAULT_SAFE_TITLE = 'Spoiler-protected content';
const DEFAULT_SAFE_SUMMARY =
  'Content hidden behind spoiler protection. Complete the required reveal to unlock.';

/**
 * Pure mapper: validates unknown API response against expected proof ID.
 */
export function parseProofDetailResponse(
  raw: unknown,
  expectedProofId: string
): ProofDetailResult {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {
      kind: 'ERROR',
      error: 'Malformed proof response: expected an object envelope',
    };
  }

  const rawObj = raw as Record<string, unknown>;

  if (!('data' in rawObj)) {
    return {
      kind: 'ERROR',
      error: 'Malformed proof response: missing "data" property',
    };
  }

  // { data: null } indicates legitimate empty / not found state
  if (rawObj.data === null) {
    return { kind: 'EMPTY' };
  }

  if (typeof rawObj.data !== 'object' || Array.isArray(rawObj.data)) {
    return {
      kind: 'ERROR',
      error: 'Malformed proof record: expected an object',
    };
  }

  const record = rawObj.data as Record<string, unknown>;

  // Validate proof_id presence and match against requested ID
  if (
    !('proof_id' in record) ||
    typeof record.proof_id !== 'string' ||
    !record.proof_id.trim()
  ) {
    return {
      kind: 'ERROR',
      error: 'Malformed proof record: missing or empty proof_id',
    };
  }

  const proofId = record.proof_id.trim();
  if (proofId !== expectedProofId) {
    return {
      kind: 'ERROR',
      error: `Mismatched proof_id: expected "${expectedProofId}", got "${proofId}"`,
    };
  }

  const workId =
    typeof record.work_id === 'string' && record.work_id.trim()
      ? record.work_id.trim()
      : null;

  const proofType =
    typeof record.proof_type === 'string' && record.proof_type.trim()
      ? record.proof_type.trim()
      : null;

  // Determine visibility
  const isLocked = Boolean(record.is_locked);
  const isVisible = record.visibility === 'VISIBLE' && !isLocked;

  // --------------------------------------------------------------------------
  // PROTECTED BRANCH
  // (LOCKED, MASKED, UNKNOWN, missing visibility, or is_locked: true)
  // NEVER read or access raw title, scene, time, explanations, or premises.
  // --------------------------------------------------------------------------
  if (!isVisible) {
    const visibilityStr =
      typeof record.visibility === 'string' && record.visibility.trim()
        ? record.visibility.trim()
        : 'LOCKED';

    const isUnderReview =
      record.human_review_status === 'PENDING' ||
      record.verification_status === 'UNREVIEWED' ||
      visibilityStr === 'UNDER_REVIEW' ||
      visibilityStr === 'PENDING_REVIEW';

    let safeTitle = isUnderReview
      ? 'Interpretation Awaiting Review'
      : 'Spoiler-Protected Interpretation';

    let safeSummary = isUnderReview
      ? 'Interpretation awaiting review.'
      : 'This interpretation contains spoilers beyond your viewing progress.';

    if (
      record.safe_preview &&
      typeof record.safe_preview === 'object' &&
      !Array.isArray(record.safe_preview)
    ) {
      const preview = record.safe_preview as Record<string, unknown>;
      if (typeof preview.title === 'string' && preview.title.trim()) {
        const candidate = preview.title.trim();
        // Do not leak internal enum names
        if (!['PROOF_ANALYSIS', 'FAN_THEORY', 'CANON_EVIDENCE'].includes(candidate.toUpperCase())) {
          safeTitle = candidate;
        }
      }
      if (typeof preview.summary === 'string' && preview.summary.trim()) {
        safeSummary = preview.summary.trim();
      }
    }

    return {
      kind: 'PROTECTED',
      proof: {
        kind: 'PROTECTED',
        proofId,
        workId,
        visibility: visibilityStr,
        isLocked: true,
        safeTitle,
        safeSummary,
        proofType,
        isUnderReview,
      },
    };
  }

  // --------------------------------------------------------------------------
  // VISIBLE BRANCH
  // (visibility === 'VISIBLE' and is_locked is not true)
  // Read verified visible fields with strict type validation.
  // --------------------------------------------------------------------------
  const title =
    typeof record.title === 'string' && record.title.trim()
      ? record.title.trim()
      : 'Untitled Proof';

  const blindExplanation =
    typeof record.blind_explanation === 'string' && record.blind_explanation.trim()
      ? record.blind_explanation.trim()
      : null;

  const revealExplanation =
    typeof record.reveal_explanation === 'string' && record.reveal_explanation.trim()
      ? record.reveal_explanation.trim()
      : null;

  const verificationStatus =
    typeof record.verification_status === 'string' && record.verification_status.trim()
      ? record.verification_status.trim()
      : null;

  const trustNamespace =
    typeof record.trust_namespace === 'string' && record.trust_namespace.trim()
      ? record.trust_namespace.trim()
      : null;

  const trustLabel =
    typeof record.trust_label === 'string' && record.trust_label.trim()
      ? record.trust_label.trim()
      : null;

  const humanReviewStatus =
    typeof record.human_review_status === 'string' && record.human_review_status.trim()
      ? record.human_review_status.trim()
      : null;

  const observedPremises: ObservedPremiseViewModel[] = [];
  if (Array.isArray(record.observed_premises)) {
    for (let i = 0; i < record.observed_premises.length; i++) {
      const item = record.observed_premises[i];
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        continue;
      }
      const prem = item as Record<string, unknown>;
      const eventId =
        typeof prem.event_id === 'string' && prem.event_id.trim()
          ? prem.event_id.trim()
          : typeof prem.fact_id === 'string' && prem.fact_id.trim()
          ? prem.fact_id.trim()
          : null;

      const sceneId =
        typeof prem.scene_id === 'string' && prem.scene_id.trim()
          ? prem.scene_id.trim()
          : typeof prem.scene_id === 'number' && !isNaN(prem.scene_id)
          ? String(prem.scene_id)
          : null;

      const timestampMs =
        typeof prem.timestamp_ms === 'number' &&
        !isNaN(prem.timestamp_ms) &&
        isFinite(prem.timestamp_ms)
          ? prem.timestamp_ms
          : null;

      const timestampFormatted =
        timestampMs !== null && timestampMs >= 0
          ? `[${[Math.floor(timestampMs / 3600000), Math.floor(timestampMs / 60000) % 60, Math.floor(timestampMs / 1000) % 60].map(value => String(value).padStart(2, '0')).join(':')}]`
          : null;

      const text =
        typeof prem.fact === 'string'
          ? prem.fact
          : typeof prem.display_fact === 'string'
          ? prem.display_fact
          : typeof prem.action === 'string'
          ? prem.action
          : '';

      const frameIds = Array.isArray(prem.evidence_frame_ids) ? prem.evidence_frame_ids : prem.frame_ids;
      const editionId = typeof record.edition_id === 'string' ? record.edition_id : null;
      const frameUrl =
        typeof prem.frame_url === 'string' && prem.frame_url.trim()
          ? prem.frame_url.trim()
          : (workId && editionId && Array.isArray(frameIds) && typeof frameIds[0] === 'string')
          ? `/api/v1/media/${encodeURIComponent(workId)}/${encodeURIComponent(editionId)}/frames/${encodeURIComponent(frameIds[0])}`
          : null;

      observedPremises.push({
        key: eventId || `premise-${i}`,
        eventId,
        sceneId,
        timestampMs,
        timestampFormatted,
        text,
        frameUrl,
      });
    }
  }

  return {
    kind: 'VISIBLE',
    proof: {
      kind: 'VISIBLE',
      proofId,
      workId,
      title,
      alternativeExplanations: Array.isArray(record.alternative_explanations) ? record.alternative_explanations.filter((value): value is string => typeof value === 'string') : [],
      blindExplanation,
      revealExplanation,
      proofType,
      verificationStatus,
      trustNamespace,
      trustLabel,
      humanReviewStatus,
      observedPremises,
    },
  };
}
