/**
 * Reframe V7 Frontend TypeScript API Contracts & DTOs
 * Complete mirror of backend schemas, trust namespaces, and proof models.
 * Zero Paid Model Calls.
 */

export type HumanReviewStatus = "VERIFIED_CANONICAL" | "NEEDS_CORRECTION" | "NOT_REVIEWED" | "APPROVED" | "REJECTED";
export type TrustNamespace = "OBSERVED_EVIDENCE" | "CANONICAL_FACT" | "CANONICAL_VERIFIED" | "ENGINE_INFERENCE" | "COMMUNITY_INTERPRETATION" | "SPECULATIVE_FAN_THEORY";
export type SpoilerVisibility = "VISIBLE" | "MASKED" | "LOCKED";
export type UserRole = "GUEST" | "USER" | "ADMIN" | "MODERATOR" | "TRUSTED_REVIEWER";

export interface ObservedPremise {
  event_id?: string;
  fact_id?: string;
  scene_id: string;
  timestamp_ms: number;
  actor?: string;
  action?: string;
  fact?: string;
  display_fact?: string;
  canonical_content_hash?: string;
}

export interface EvidenceChainItem {
  scene_id: string;
  timestamp_ms: number;
  scene_summary?: string;
}

export interface ProofCardDTO {
  moment_id?: string;
  proof_id: string;
  work_id: string;
  edition_id: string;
  reveal_id: string;
  proof_type: "KNOWLEDGE_LEAK" | "CLAIM_ACTION_CONFLICT" | "HIDDEN_PLAN_CHAIN" | "MULTI_SCENE_PATTERN" | "MECHANISM_DISCOVERY" | string;
  title: string;
  blind_explanation: string;
  reveal_explanation: string;
  evidence_chain: EvidenceChainItem[];
  observed_premises: ObservedPremise[];
  alternative_explanations: string[];
  counterfactual_results?: {
    wrong_reveal_delta?: number;
    ablation_delta?: number;
    reveal_swap_delta?: number;
    evidence_ablation_delta?: number;
    is_counterfactually_robust?: boolean;
  };
  counterfactual_robustness?: {
    reveal_swap_delta?: number;
    verdict?: string;
  };
  proof_badge?: string;
  verification_status?: string;
  proof_strength: number;
  fan_impact: number;
  human_review_status: HumanReviewStatus;
  presentation_status?: string;
  trust_namespace: TrustNamespace;
  trust_label: string;
  scene_id?: string;
  reframed_timestamp_ms?: number;
  reveal_timestamp_ms?: number;
  clue_description?: string;
}

export interface ApiResponseMeta {
  total?: number;
  offset?: number;
  limit?: number;
  request_id?: string;
  next_cursor?: string | null;
}

export interface FilmDTO {
  registered_at?: string | null;
  view_count?: number;
  views_7d?: number;
  movie_id: string;
  edition_id: string;
  title: string;
  title_ko?: string | null;
  year: number;
  synopsis_safe: string;
  runtime_ms: number;
  rights_status: string;
  analysis_status: string;
  canonical_asset_sha256?: string;
  dataset_version?: string;
  reveals_count?: number;
  scenes_count?: number;
  available_modes?: string[];
  viewer_progress_ms?: number;
  viewer_state?: string;
  poster_path?: string | null;
  directors?: Array<{ qid?: string; name_en?: string; name_ko?: string }>;
  cast?: Array<{ qid?: string; name_en?: string; name_ko?: string }>;
  genres?: string[];
  core_demo_supported?: boolean;
}

export interface RevealSummaryDTO {
  reveal_id: string;
  work_id: string;
  edition_id: string;
  title: string;
  timestamp_ms: number;
  spoiler_cutoff_ms: number;
  severity: string;
  safe_title: string;
  visibility: SpoilerVisibility;
  description?: string;
  safe_preview?: {
    title: string;
    summary?: string | null;
  };
}

export interface RevealDTO extends RevealSummaryDTO {
  character_or_subject?: string;
  previous_belief?: string;
  revealed_fact?: string;
  affected_entities?: string[];
  evidence_scene_ids?: string[];
  proof_count?: number;
}

export interface WatchProgressDTO {
  work_id: string;
  edition_id: string;
  state: string;
  progress_ms: number;
  completed_reveal_ids: string[];
  updated_at?: string;
}

export interface SpoilerPreferencesDTO {
  default_mode: string;
  mask_titles: boolean;
  mask_thumbnails: boolean;
  mask_comments: boolean;
}

export interface UserProfileDTO {
  avatar_url?: string | null;
  id: string | null;
  email?: string | null;
  display_name: string;
  role: UserRole;
  fan_depth: string;
  spoiler_preferences: SpoilerPreferencesDTO;
}

export interface AuthUserDTO {
  user_id: string;
  email: string;
  display_name: string;
  role: UserRole;
  fan_depth: string;
  csrf_token: string;
}

export interface CsrfResponseDTO {
  csrf_token: string;
}

export interface TheoryValidationResultDTO {
  run_id?: string;
  theory_id?: string;
  status?: string;
  post_version_id?: string;
  target_reveal_id?: string;
  work_id?: string;
  validation_verdict: string;
  validation_mode?: string;
  trust_namespace?: string;
  live_model_used?: boolean;
  grounding_score: number;
  supporting_evidence?: any[];
  counterevidence?: any[];
  missing_evidence?: any[];
  alternative_explanations?: string[];
  counterfactual_results?: Record<string, any>;
  uncertainty?: number | null;
  evidence_details?: Array<{event_id: string; scene_id: string; timestamp_ms: number; description: string}>;
  input_hash?: string;
  created_at?: string;
  completed_at?: string;
}

export interface TheoryDTO {
  theory_id: string;
  author_id: string;
  work_id: string;
  edition_id: string;
  status: "DRAFT" | "PUBLISHED";
  title: string;
  body_markdown: string;
  version_no: number;
  created_at?: string;
  target_reveal_id?: string;
}

export interface PostVersionDTO {
  version_id: string;
  version_no: number;
  title: string;
  body_markdown: string;
  created_at: string;
}

export interface ClaimDTO {
  claim_id: string;
  text: string;
  classification: string;
  status: string;
}

export interface CounterclaimDTO {
  counterclaim_id?: string;
  id?: string;
  target_claim_id?: string;
  author_name: string;
  challenged_premise: string;
  alternative_explanation: string;
  status?: string;
  created_at?: string;
}

export interface CommunityCommentDTO {
  comment_id?: string;
  id?: string;
  author_name?: string;
  author_id?: string;
  body_markdown?: string;
  content?: string;
  comment_type?: string;
  created_at?: string;
}

export interface CommunityPostDTO {
  contains_spoilers?: boolean;
  is_spoiler_masked?: boolean;
  version_no?: number;
  rating?: number | null;
  author_cutoff_ms?: number | null;
  is_locked?: boolean;
  visibility?: string;
  likes_count?: number;
  post_id: string;
  id?: string;
  author_id?: string;
  author_name: string;
  work_id: string;
  edition_id: string;
  content_type: string;
  status: string;
  title: string;
  body_markdown: string;
  body_sanitized_html?: string;
  published_at?: string;
  created_at?: string;
  claims?: ClaimDTO[];
  counterclaims?: CounterclaimDTO[];
  comments?: CommunityCommentDTO[];
  evidence_links?: Array<{ evidence_type: string; evidence_id: string; relation: string; annotation?: string }>;
  reactions_count?: Record<string, number> | number;
  is_synthetic?: boolean;
  content_origin?: string;
  ai_disclosure?: string;
}


export interface SceneDTO {
  scene_id: string;
  start_ms: number;
  end_ms: number;
  summary: string;
  characters: string[];
  objects: string[];
  canonical_content_hash?: string;
}
