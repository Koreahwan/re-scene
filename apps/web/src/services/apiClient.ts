/**
 * Reframe V7 Frontend Typed API Client
 * Modular API client with centralized error handling, CSRF synchronization,
 * and pure HttpOnly cookie authentication (no raw JWTs stored in browser storage).
 * Zero Paid Model Calls.
 */
import {
  FilmDTO,
  RevealDTO,
  RevealSummaryDTO,
  ProofCardDTO,
  UserProfileDTO,
  AuthUserDTO,
  WatchProgressDTO,
  SpoilerPreferencesDTO,
  TheoryDTO,
  TheoryValidationResultDTO,
  CommunityPostDTO,
  SceneDTO,
  ApiResponseMeta
} from '../types/api';

import type {
  LoginRequest,
  SignupRequest,
  EmailVerificationRequest,
  EmailVerificationConfirmRequest,
  PasswordResetRequest,
  PasswordResetVerifyRequest,
  PasswordResetCompleteRequest,
  CreatePostRequest,
  CreateCommentRequest,
  AddReactionRequest,
  CreateCounterclaimRequest,
  CreateTheoryRequest,
  CreateTheoryRunRequest,
  CreateAudienceRunRequest,
  UpdateWatchProgressRequest,
  UpdateSpoilerPreferencesRequest
} from '../generated/api-types';

export type {
  LoginRequest,
  SignupRequest,
  EmailVerificationRequest,
  EmailVerificationConfirmRequest,
  PasswordResetRequest,
  PasswordResetVerifyRequest,
  PasswordResetCompleteRequest,
  CreatePostRequest,
  CreateCommentRequest,
  AddReactionRequest,
  CreateCounterclaimRequest,
  CreateTheoryRequest,
  CreateTheoryRunRequest,
  CreateAudienceRunRequest,
  UpdateWatchProgressRequest,
  UpdateSpoilerPreferencesRequest
};

import type { SelectedPortion } from './selectedPortion';

const API_BASE = '/api/v1';

export async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMessage = `Request failed with status ${res.status}`;
    try {
      const err = await res.json();
      if (err?.error?.message) errorMessage = err.error.message;
      else if (err?.detail) errorMessage = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
    } catch {}
    throw new Error(errorMessage);
  }
  if (res.status === 204) {
    return {} as T;
  }
  return res.json();
}

class ApiError extends Error {
  public status: number;
  public code?: string;
  public details?: any;

  constructor(message: string, status: number, code?: string, details?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

class BaseApiClient {
  private static sharedCsrfToken: string | null = null;
  private activeLocale: string = 'en-US';

  public setCsrfToken(token: string | null) {
    BaseApiClient.sharedCsrfToken = token;
  }

  public getCsrfToken(): string | null {
    return BaseApiClient.sharedCsrfToken;
  }

  public setLocale(locale: string) {
    this.activeLocale = locale;
  }

  public getLocale(): string {
    return this.activeLocale;
  }

  protected async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const method = (options.method || 'GET').toUpperCase();
    if (!BaseApiClient.sharedCsrfToken && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && !endpoint.includes('/auth/csrf')) {
      try {
        const csrfRes = await fetch(`${API_BASE}/auth/csrf`, { credentials: 'include' });
        if (csrfRes.ok) {
          const csrfJson = await csrfRes.json();
          if (csrfJson.data?.csrf_token) {
            BaseApiClient.sharedCsrfToken = csrfJson.data.csrf_token;
          }
        }
      } catch {}
    }

    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept-Language': this.activeLocale,
      ...(options.headers as Record<string, string> || {})
    };

    if (BaseApiClient.sharedCsrfToken && !headers['X-CSRF-Token']) {
      headers['X-CSRF-Token'] = BaseApiClient.sharedCsrfToken;
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include'
    });


    if (!response.ok) {
      let errorMessage = `Request failed with status ${response.status}`;
      let errorCode = 'API_ERROR';
      let details: any = null;

      try {
        const errorJson = await response.json();
        if (errorJson.error) {
          errorMessage = errorJson.error.message || errorMessage;
          errorCode = errorJson.error.code || errorCode;
          details = errorJson.error.details;
        } else if (errorJson.detail) {
          errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        } else if (errorJson.message) {
          errorMessage = errorJson.message;
        }
      } catch {
        // use default message
      }

      throw new ApiError(errorMessage, response.status, errorCode, details);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }
}

export class AuthApi extends BaseApiClient {
  async getDemoAccount(): Promise<{ data: { enabled: boolean; email?: string; password?: string } }> {
    return this.request('/auth/demo-account');
  }

  async getCsrf(): Promise<{ data: { csrf_token: string } }> {
    const res = await this.request<{ data: { csrf_token: string } }>('/auth/csrf');
    if (res.data?.csrf_token) {
      this.setCsrfToken(res.data.csrf_token);
    }
    return res;
  }

  async getMe(): Promise<{ data: UserProfileDTO }> {
    return this.request<{ data: UserProfileDTO }>('/auth/me');
  }

  async checkHandleAvailability(handle: string): Promise<{ data: { handle: string; available: boolean } }> {
    return this.request<{ data: { handle: string; available: boolean } }>(`/auth/handles/availability?handle=${encodeURIComponent(handle)}`);
  }

  async signup(payload: {
    email: string;
    password: string;
    email_verification_ticket: string;
    display_name?: string;
    handle?: string;
    locale?: string;
  }): Promise<{ data: AuthUserDTO }> {
    const res = await this.request<{ data: AuthUserDTO }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    if (res.data?.csrf_token) {
      this.setCsrfToken(res.data.csrf_token);
    }
    return res;
  }

  async login(payload: { email: string; password: string }): Promise<{ data: AuthUserDTO }> {
    const res = await this.request<{ data: AuthUserDTO }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    if (res.data?.csrf_token) {
      this.setCsrfToken(res.data.csrf_token);
    }
    return res;
  }

  async logout(): Promise<{ data: { logged_out: boolean } }> {
    const res = await this.request<{ data: { logged_out: boolean } }>('/auth/logout', {
      method: 'POST'
    });
    this.setCsrfToken(null);
    return res;
  }

  async devLogin(email: string = 'fan@reframe.dev', displayName: string = 'Fan Investigator'): Promise<{ data: AuthUserDTO }> {
    const res = await this.request<{ data: AuthUserDTO }>('/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ email, display_name: displayName })
    });
    if (res.data?.csrf_token) {
      this.setCsrfToken(res.data.csrf_token);
    }
    return res;
  }

  async requestEmailVerification(email: string): Promise<{ data: { sent: boolean; expires_in_seconds: number } }> {
    return this.request<{ data: { sent: boolean; expires_in_seconds: number } }>('/auth/email-verification/request', {
      method: 'POST',
      body: JSON.stringify({ email })
    });
  }

  async confirmEmailVerification(email: string, code: string): Promise<{ data: { verified: boolean; email_verification_ticket: string } }> {
    return this.request<{ data: { verified: boolean; email_verification_ticket: string } }>('/auth/email-verification/confirm', {
      method: 'POST',
      body: JSON.stringify({ email, code })
    });
  }

  async requestPasswordReset(email: string): Promise<{ data: { sent: boolean; expires_in_seconds: number } }> {
    return this.request<{ data: { sent: boolean; expires_in_seconds: number } }>('/auth/password-reset/request', {
      method: 'POST',
      body: JSON.stringify({ email })
    });
  }

  async verifyPasswordReset(email: string, code: string): Promise<{ data: { valid: boolean; password_reset_ticket: string } }> {
    return this.request<{ data: { valid: boolean; password_reset_ticket: string } }>('/auth/password-reset/verify', {
      method: 'POST',
      body: JSON.stringify({ email, code })
    });
  }

  async completePasswordReset(email: string, passwordResetTicket: string, newPassword: string): Promise<{ data: { updated: boolean } }> {
    return this.request<{ data: { updated: boolean } }>('/auth/password-reset/complete', {
      method: 'POST',
      body: JSON.stringify({ email, password_reset_ticket: passwordResetTicket, new_password: newPassword })
    });
  }

  async getDevOutbox(): Promise<{ data: Array<{ recipient: string; purpose: string; raw_code: string; expires_at: string }> }> {
    return this.request<{ data: Array<{ recipient: string; purpose: string; raw_code: string; expires_at: string }> }>('/dev/auth/outbox');
  }
}



export class CatalogApi extends BaseApiClient {
  async getAllFilms(): Promise<{ data: FilmDTO[]; meta?: ApiResponseMeta }> {
    const data: FilmDTO[] = [];
    while (true) {
      const page = await this.getFilms({ offset: data.length, limit: 50 });
      if (!Array.isArray(page.data)) throw new Error('Malformed film catalog');
      const previousLength = data.length;
      data.push(...page.data);
      if (page.data.length === 0 || data.length >= (page.meta?.total ?? data.length)) break;
      if (new Set(data.map(film => film.movie_id)).size !== data.length || data.length <= previousLength) {
        throw new Error('Film catalog pagination did not advance');
      }
    }
    return { data, meta: { total: data.length } };
  }
  async getFilms(options?: { q?: string; offset?: number; limit?: number }): Promise<{
    data: FilmDTO[];
    meta?: ApiResponseMeta;
  }> {
    const params = new URLSearchParams();
    if (options?.q) params.set('q', options.q);
    if (options?.offset !== undefined) params.set('offset', String(options.offset));
    if (options?.limit !== undefined) params.set('limit', String(options.limit));
    const qs = params.toString();
    return this.request<{
      data: FilmDTO[];
      meta?: ApiResponseMeta;
    }>(qs ? `/films?${qs}` : '/films');
  }

  async getFilmDetail(movieId: string = 'the-bat-whispers-1930', editionId?: string): Promise<{ data: FilmDTO }> {
    return this.request<{ data: FilmDTO }>(`/films/${encodeURIComponent(movieId)}${editionId ? `?edition_id=${encodeURIComponent(editionId)}` : ''}`);
  }

  async getSelectedPortion(movieId: string, editionId: string, selectedMs: number, signal?: AbortSignal): Promise<{ data: SelectedPortion }> {
    const params = new URLSearchParams({ edition_id: editionId, selected_ms: String(selectedMs) });
    return this.request(`/films/${encodeURIComponent(movieId)}/selected-portion-analysis?${params}`, { signal, cache: 'no-store' });
  }

  async getReveals(movieId: string = 'the-bat-whispers-1930', editionId?: string, watchedOnly = false): Promise<{ data: RevealSummaryDTO[] }> {
    const params = new URLSearchParams();
    if (editionId) params.set('edition_id', editionId);
    if (watchedOnly) params.set('watched_only', 'true');
    return this.request<{ data: RevealSummaryDTO[] }>(`/films/${encodeURIComponent(movieId)}/reveals${params.size ? `?${params}` : ''}`);
  }

  async getRevealDetail(revealId: string): Promise<{ data: RevealDTO }> {
    return this.request<{ data: RevealDTO }>(`/reveals/${revealId}`);
  }

  async getSceneDetail(sceneId: string): Promise<{ data: SceneDTO }> {
    return this.request<{ data: SceneDTO }>(`/fan/scenes/${sceneId}`);
  }

  async getSceneIndex(movieId: string, editionId?: string): Promise<{ data: Array<{scene_id: string; start_ms: number; end_ms: number}> }> {
    return this.request(`/films/${encodeURIComponent(movieId)}/scene-index${editionId ? `?edition_id=${encodeURIComponent(editionId)}` : ''}`);
  }
}

export class ProofApi extends BaseApiClient {
  async getProofsForReveal(revealId: string, watchedOnly = false): Promise<{ data: ProofCardDTO[] }> {
    return this.request<{ data: ProofCardDTO[] }>(`/reveals/${encodeURIComponent(revealId)}/proofs${watchedOnly ? '?watched_only=true' : ''}`);
  }

  async getProofById(proofId: string): Promise<{ data: ProofCardDTO }> {
    return this.request<{ data: ProofCardDTO }>(`/proofs/${proofId}`);
  }

  async getProofComments(proofId: string): Promise<{ data: any[] }> {
    return this.request<{ data: any[] }>(`/proofs/${proofId}/comments`);
  }

  async createProofComment(proofId: string, payload: { body_markdown: string; parent_comment_id?: string | null; contains_spoilers?: boolean }, requestKey?: string): Promise<{ data: any }> {
    return this.request<{ data: any }>(`/proofs/${proofId}/comments`, {
      method: 'POST',
      headers: requestKey ? { 'Idempotency-Key': requestKey } : undefined,
      body: JSON.stringify(payload),
    });
  }

  async getProofReactions(proofId: string): Promise<{ data: { proof_id: string; like_count: number; viewer_liked: boolean } }> {
    return this.request<{ data: { proof_id: string; like_count: number; viewer_liked: boolean } }>(`/proofs/${proofId}/reactions`);
  }

  async putProofReaction(proofId: string, liked: boolean): Promise<{ data: any }> {
    return this.request<{ data: any }>(`/proofs/${proofId}/reactions`, {
      method: 'PUT',
      body: JSON.stringify({ liked, reaction_type: 'LIKE' }),
    });
  }
}

export class TheoryApi extends BaseApiClient {
  async createTheory(payload: {
    title: string;
    hypothesis_explanation: string;
    target_reveal_id: string;
    work_id?: string;
    edition_id?: string;
  }): Promise<{ data: { theory_id: string; status: string } }> {
    return this.request<{ data: { theory_id: string; status: string } }>('/theories', {
      method: 'POST',
      body: JSON.stringify({
        work_id: payload.work_id || 'the-bat-whispers-1930',
        edition_id: payload.edition_id || 'tbw-fullscreen-archive',
        target_reveal_id: payload.target_reveal_id,
        title: payload.title,
        hypothesis_explanation: payload.hypothesis_explanation
      })
    });
  }

  async getTheory(theoryId: string): Promise<{ data: TheoryDTO }> {
    return this.request<{ data: TheoryDTO }>(`/theories/${theoryId}`);
  }

  async updateTheory(theoryId: string, payload: { title?: string; hypothesis_explanation?: string; change_summary?: string; target_reveal_id?: string }): Promise<{ data: TheoryDTO }> {
    return this.request<{ data: TheoryDTO }>(`/theories/${theoryId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    });
  }

  async publishTheory(theoryId: string): Promise<{ data: { theory_id: string; status: string } }> {
    return this.request<{ data: { theory_id: string; status: string } }>(`/theories/${theoryId}/publish`, {
      method: 'POST'
    });
  }

  async submitTheoryRun(payload: {
    theory_id: string;
    target_reveal_id: string;
    work_id?: string;
    edition_id?: string;
  }): Promise<{ data: { run_id: string; status: string; events_url: string } }> {
    const idempotencyKey = `idemp-theory-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    return this.request<{ data: { run_id: string; status: string; events_url: string } }>('/theory-runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({
        theory_id: payload.theory_id,
        work_id: payload.work_id || 'the-bat-whispers-1930',
        edition_id: payload.edition_id || 'tbw-fullscreen-archive',
        target_reveal_id: payload.target_reveal_id
      })
    });
  }

  async getTheoryRun(runId: string): Promise<{ data: TheoryValidationResultDTO }> {
    return this.request<{ data: TheoryValidationResultDTO }>(`/theory-runs/${runId}`);
  }
}

export class CommunityApi extends BaseApiClient {
  async getTopBoxReviewTarget(pageId: number): Promise<{ data: { work_id: string; edition_id: string; title: string; own_post_id: string | null } }> {
    return this.request(`/community/top-box/${pageId}/review-target`);
  }
  async listPosts(workId: string = 'the-bat-whispers-1930', origin?: string, sort?: string): Promise<{ data: CommunityPostDTO[] }> {
    const params = new URLSearchParams({ work_id: workId });
    if (origin) params.append('origin', origin);
    if (sort) params.append('sort', sort);
    return this.request<{ data: CommunityPostDTO[] }>(`/community/posts?${params.toString()}`);
  }

  async getPostDetail(postId: string): Promise<{ data: CommunityPostDTO }> {
    return this.request<{ data: CommunityPostDTO }>(`/community/posts/${postId}`);
  }

  async getPost(postId: string): Promise<{ data: CommunityPostDTO }> {
    return this.request<{ data: CommunityPostDTO }>(`/community/posts/${postId}`);
  }

  async createPost(payload: {
    idempotency_key?: string;
    work_id?: string;
    edition_id?: string;
    content_type?: string;
    title: string;
    body_markdown: string;
    claim_text?: string;
    claim_classification?: string;
    evidence_links?: Array<{ evidence_type: string; evidence_id: string; relation?: string; annotation?: string }>;
    tagged_reveal_ids?: string[];
    ai_disclosure?: string;
    rating?: number;
    contains_spoilers?: boolean;
    author_cutoff_ms?: number;
  }): Promise<{ status: string; data: { post_id: string; status: string; published_at?: string } }> {
    return this.request<{ status: string; data: { post_id: string; status: string; published_at?: string } }>('/community/posts', {
      method: 'POST',
      headers: payload.idempotency_key ? { 'Idempotency-Key': payload.idempotency_key } : undefined,
      body: JSON.stringify({
        work_id: payload.work_id || 'the-bat-whispers-1930',
        edition_id: payload.edition_id || (payload.work_id && payload.work_id !== 'the-bat-whispers-1930' ? `${payload.work_id}-catalog` : 'tbw-fullscreen-archive'),
        content_type: payload.content_type || 'FAN_THEORY',
        title: payload.title,
        body_markdown: payload.body_markdown,
        claim_text: payload.claim_text,
        claim_classification: payload.claim_classification || 'STRONG_INTERPRETATION',
        evidence_links: payload.evidence_links || [],
        tagged_reveal_ids: payload.tagged_reveal_ids || [],
        ai_disclosure: payload.ai_disclosure || 'HUMAN',
        rating: payload.rating,
        contains_spoilers: payload.contains_spoilers,
        author_cutoff_ms: payload.author_cutoff_ms,
      })
    });
  }

  async updatePost(postId: string, payload: { title?: string; body_markdown?: string; expected_version: number; rating?: number; contains_spoilers?: boolean; author_cutoff_ms?: number }): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>(`/community/posts/${postId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    });
  }

  async deletePost(postId: string): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>(`/community/posts/${postId}`, {
      method: 'DELETE'
    });
  }

  async listComments(postId: string): Promise<{ status: string; data: any[] }> {
    return this.request<{ status: string; data: any[] }>(`/community/posts/${postId}/comments`);
  }

  async createComment(postId: string, bodyMarkdown: string, parentCommentId?: string, authorCutoffMs?: number, containsSpoilers = false, requestKey?: string): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>(`/community/posts/${postId}/comments`, {
      method: 'POST',
      headers: requestKey ? { 'Idempotency-Key': requestKey } : undefined,
      body: JSON.stringify({
        body_markdown: bodyMarkdown,
        parent_comment_id: parentCommentId || null,
        author_cutoff_ms: authorCutoffMs,
        contains_spoilers: containsSpoilers,
      })
    });
  }

  async updateComment(postId: string, commentId: string, payload: { body_markdown: string; expected_version: number; author_cutoff_ms?: number; contains_spoilers?: boolean }): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>(`/community/posts/${postId}/comments/${commentId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    });
  }

  async deleteComment(postId: string, commentId: string): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>(`/community/posts/${postId}/comments/${commentId}`, {
      method: 'DELETE'
    });
  }

  async putReaction(postId: string, liked: boolean, reactionType: string = 'LIKE'): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>(`/community/posts/${postId}/reactions`, {
      method: 'PUT',
      body: JSON.stringify({ reaction_type: reactionType, liked })
    });
  }

  async unlockContent(contentType: 'POST' | 'COMMENT', contentId: string, versionNo: number = 1): Promise<{ status: string; data: any }> {
    return this.request<{ status: string; data: any }>('/viewer/unlock', {
      method: 'POST',
      body: JSON.stringify({ content_type: contentType, content_id: contentId, version_no: versionNo })
    });
  }

  async reactToPost(postId: string, reactionType: string): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/community/posts/${postId}/reactions`, {
      method: 'POST',
      body: JSON.stringify({ reaction_type: reactionType })
    });
  }

  async createCounterclaim(postId: string, payload: {
    target_claim_id: string;
    challenged_premise: string;
    alternative_explanation: string;
    evidence_links?: Array<{ evidence_type: string; evidence_id: string; relation?: string; annotation?: string }>;
  }): Promise<{ status: string; data: { counterclaim_id: string; status: string } }> {
    return this.request<{ status: string; data: { counterclaim_id: string; status: string } }>(`/community/posts/${postId}/counterclaims`, {
      method: 'POST',
      body: JSON.stringify({
        target_claim_id: payload.target_claim_id,
        challenged_premise: payload.challenged_premise,
        alternative_explanation: payload.alternative_explanation,
        evidence_links: payload.evidence_links || []
      })
    });
  }
}

export interface WishlistFilmDTO {
  movie_id: string;
  title: string;
  poster_path: string | null;
  created_at: string;
}

export interface MyReviewDTO extends WishlistFilmDTO {
  destination?: string;
  post_id: string;
  rating: number;
  body_markdown: string;
  version_no: number;
  contains_spoilers: boolean;
}

export class ProfileApi extends BaseApiClient {
  getMyReviews(page = 1) {
    return this.request<{ data: MyReviewDTO[]; meta: { total: number } }>(`/me/reviews?offset=${(page - 1) * 12}&limit=12`);
  }

  getWishlist(page = 1) {
    return this.request<{ data: WishlistFilmDTO[]; meta: { total: number } }>(`/me/wishlist?offset=${(page - 1) * 12}&limit=12`);
  }

  getWishlistState(workId: string) {
    return this.request<{ data: { saved: boolean } }>(`/me/wishlist/${encodeURIComponent(workId)}`);
  }

  setWishlist(workId: string, saved: boolean) {
    return this.request<{ data: { saved: boolean } }>(`/me/wishlist/${encodeURIComponent(workId)}`, { method: 'PUT', body: JSON.stringify({ saved }) });
  }

  updateProfile(payload: { display_name: string; photo_data?: string | null }) {
    return this.request<{ data: { display_name: string; avatar_url: string | null } }>('/profiles/me', { method: 'PATCH', body: JSON.stringify(payload) });
  }
  async getWatchProgress(): Promise<{ data: WatchProgressDTO[] }> {
    return this.request<{ data: WatchProgressDTO[] }>('/me/watch-progress');
  }

  async updateWatchProgress(workId: string, payload: {
    edition_id: string;
    state: string;
    progress_ms: number;
    completed_reveal_ids: string[];
  }): Promise<{ data: WatchProgressDTO }> {
    return this.request<{ data: WatchProgressDTO }>(`/me/watch-progress/${workId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  async getSpoilerPreferences(): Promise<{ data: SpoilerPreferencesDTO }> {
    return this.request<{ data: SpoilerPreferencesDTO }>('/me/spoiler-preferences');
  }

  async updateSpoilerPreferences(payload: SpoilerPreferencesDTO): Promise<{ data: SpoilerPreferencesDTO }> {
    return this.request<{ data: SpoilerPreferencesDTO }>('/me/spoiler-preferences', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }
}


export class MagazineApi extends BaseApiClient {
  async listArticles(
    workIdOrParams?: string | { work_id?: string; workId?: string; article_type?: string; articleType?: string },
    articleType?: string
  ): Promise<{
    articles: any[];
    total: number;
    disclaimer: string;
  }> {
    let workId: string | undefined = undefined;
    let aType = articleType;
    let origin: string | undefined = undefined;

    if (typeof workIdOrParams === 'string' && workIdOrParams.trim().length > 0) {
      workId = workIdOrParams.trim();
    } else if (workIdOrParams && typeof workIdOrParams === 'object') {
      workId = workIdOrParams.work_id || workIdOrParams.workId;
      aType = workIdOrParams.article_type || workIdOrParams.articleType || aType;
      origin = (workIdOrParams as any).origin;
    }

    const params = new URLSearchParams();
    if (workId) params.append('work_id', workId);
    if (aType) params.append('article_type', aType);
    if (origin) params.append('origin', origin);
    const qs = params.toString();
    return this.request<{ articles: any[]; total: number; disclaimer: string }>(qs ? `/magazine?${qs}` : '/magazine');
  }

  async getArticle(articleId: string): Promise<any> {
    return this.request<any>(`/magazine/${encodeURIComponent(articleId)}`);
  }

  async getReactions(articleId: string): Promise<{
    status: string;
    data: { article_id: string; like_count: number; viewer_liked: boolean };
  }> {
    return this.request<{
      status: string;
      data: { article_id: string; like_count: number; viewer_liked: boolean };
    }>(`/magazine/${encodeURIComponent(articleId)}/reactions`);
  }

  async putReaction(
    articleId: string,
    liked: boolean
  ): Promise<{
    status: string;
    data: { article_id: string; like_count: number; liked: boolean };
  }> {
    return this.request<{
      status: string;
      data: { article_id: string; like_count: number; liked: boolean };
    }>(`/magazine/${encodeURIComponent(articleId)}/reactions`, {
      method: 'PUT',
      body: JSON.stringify({ reaction_type: 'LIKE', liked }),
    });
  }

  async getComments(
    articleId: string
  ): Promise<{
    status: string;
    data: any[];
    total: number;
  }> {
    return this.request<{
      status: string;
      data: any[];
      total: number;
    }>(`/magazine/${encodeURIComponent(articleId)}/comments`);
  }

  async postComment(
    articleId: string,
    bodyMarkdown: string,
    authorCutoffMs?: number,
    parentCommentId?: string | null
  ): Promise<{
    status: string;
    data: any;
  }> {
    return this.request<{
      status: string;
      data: any;
    }>(`/magazine/${encodeURIComponent(articleId)}/comments`, {
      method: 'POST',
      body: JSON.stringify({
        body_markdown: bodyMarkdown,
        author_cutoff_ms: authorCutoffMs,
        parent_comment_id: parentCommentId || null,
      }),
    });
  }
}

export class AudienceLabApi extends BaseApiClient {
  async getPersonasSummary(): Promise<any> {
    return this.request<any>('/admin/audience-lab/personas/summary');
  }

  async createRun(payload: {
    mode: string;
    unique_source_personas?: number;
    variants?: string[];
    replications?: number;
    seed?: number;
    seed_content?: boolean;
  }): Promise<any> {
    const idempotencyKey = `idem-sim-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    return this.request<any>('/admin/audience-lab/runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(payload)
    });
  }

  async getRun(runId: string): Promise<any> {
    return this.request<any>(`/admin/audience-lab/runs/${runId}`);
  }

  async getFunnel(runId: string): Promise<any> {
    return this.request<any>(`/admin/audience-lab/runs/${runId}/funnel`);
  }

  async getBottlenecks(runId: string): Promise<any> {
    return this.request<any>(`/admin/audience-lab/runs/${runId}/bottlenecks`);
  }

  async getCohorts(runId: string): Promise<any> {
    return this.request<any>(`/admin/audience-lab/runs/${runId}/cohorts`);
  }

  async getSensitivity(runId: string): Promise<any> {
    return this.request<any>(`/admin/audience-lab/runs/${runId}/sensitivity`);
  }

  async getLoadProfile(runId: string): Promise<any> {
    return this.request<any>(`/admin/audience-lab/runs/${runId}/load-profile`);
  }

  async getLatestSummary(): Promise<any> {
    return this.request<any>('/admin/audience-lab/runs/latest/summary');
  }

  async seedContent(runId?: string, payload?: any, idempotencyKey?: string): Promise<any> {
    if (!runId) {
      throw new Error("completedRunId is required to seed synthetic demo content.");
    }
    const key = idempotencyKey || `idem-seed-${runId}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    return this.request<any>(`/admin/audience-lab/runs/${runId}/seed-content`, {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify(payload || { posts_count: 20, comments_count: 40, counterclaims_count: 20, reactions_count: 60, enable_magazine: true })
    });
  }

  async purgeContent(confirmDelete: boolean = true): Promise<any> {
    return this.request<any>('/admin/audience-lab/purge-content', {
      method: 'POST',
      body: JSON.stringify({ confirm_delete_synthetic_only: confirmDelete })
    });
  }
}


// Unified client class
export class ApiClient {
  public auth: AuthApi;
  public catalog: CatalogApi;
  public proof: ProofApi;
  public theory: TheoryApi;
  public community: CommunityApi;
  public profile: ProfileApi;
  public magazine: MagazineApi;
  public audienceLab: AudienceLabApi;

  constructor() {
    this.auth = new AuthApi();
    this.catalog = new CatalogApi();
    this.proof = new ProofApi();
    this.theory = new TheoryApi();
    this.community = new CommunityApi();
    this.profile = new ProfileApi();
    this.magazine = new MagazineApi();
    this.audienceLab = new AudienceLabApi();
  }

  public setCsrfToken(token: string | null) {
    this.auth.setCsrfToken(token);
    this.catalog.setCsrfToken(token);
    this.proof.setCsrfToken(token);
    this.theory.setCsrfToken(token);
    this.community.setCsrfToken(token);
    this.profile.setCsrfToken(token);
    this.magazine.setCsrfToken(token);
    this.audienceLab.setCsrfToken(token);
  }

  public setLocale(locale: string) {
    this.auth.setLocale(locale);
    this.catalog.setLocale(locale);
    this.proof.setLocale(locale);
    this.theory.setLocale(locale);
    this.community.setLocale(locale);
    this.profile.setLocale(locale);
    this.magazine.setLocale(locale);
    this.audienceLab.setLocale(locale);
  }

  // Compatibility helpers
  async getMe() { return this.auth.getMe(); }
  async devLogin(email?: string, name?: string) { return this.auth.devLogin(email, name); }
  async getReveals(workId?: string) { return this.catalog.getReveals(workId); }
  async getProofsForReveal(revealId: string) { return this.proof.getProofsForReveal(revealId); }
  async createTheoryDraft(title: string, explanation: string, targetRevealId: string) {
    return this.theory.createTheory({ title, hypothesis_explanation: explanation, target_reveal_id: targetRevealId });
  }
  async submitTheoryValidationRun(theoryId: string, targetRevealId: string) {
    return this.theory.submitTheoryRun({ theory_id: theoryId, target_reveal_id: targetRevealId });
  }
  async getTheoryValidationResult(runId: string) {
    return this.theory.getTheoryRun(runId);
  }
  async getCommunityPosts(workId?: string, origin?: string) {
    return this.community.listPosts(workId || 'the-bat-whispers-1930', origin);
  }
}

export const apiClient = new ApiClient();

// Convenient API Singletons with compatibility aliases
export const filmsApi = {
  getSelectedPortion: (movieId: string, editionId: string, selectedMs: number, signal?: AbortSignal) => apiClient.catalog.getSelectedPortion(movieId, editionId, selectedMs, signal),
  getFilms: (options?: { q?: string; offset?: number; limit?: number }) => apiClient.catalog.getFilms(options),
  getAllFilms: () => apiClient.catalog.getAllFilms(),
  getFilm: (movieId: string, editionId?: string) => apiClient.catalog.getFilmDetail(movieId, editionId),
  getFilmDetail: (movieId: string, editionId?: string) => apiClient.catalog.getFilmDetail(movieId, editionId)
};

export const catalogApi = apiClient.catalog;

export const revealsApi = {
  getReveals: (movieId?: string, editionId?: string, watchedOnly = false) => apiClient.catalog.getReveals(movieId, editionId, watchedOnly),
  getReveal: (revealId: string) => apiClient.catalog.getRevealDetail(revealId),
  getRevealDetail: (revealId: string) => apiClient.catalog.getRevealDetail(revealId)
};

export const proofsApi = {
  getProofsForReveal: (revealId: string, watchedOnly = false) => apiClient.proof.getProofsForReveal(revealId, watchedOnly),
  getProof: (proofId: string) => apiClient.proof.getProofById(proofId),
  getProofById: (proofId: string) => apiClient.proof.getProofById(proofId)
};

export const momentsApi = {
  getMoments: (revealId: string) => apiClient.proof.getProofsForReveal(revealId),
  getProofsForReveal: (revealId: string) => apiClient.proof.getProofsForReveal(revealId)
};

export const theoryApi = apiClient.theory;

export const communityApi = {
  getPosts: (workId?: string, origin?: string, sort?: string) => apiClient.community.listPosts(workId, origin, sort),
  listPosts: (workId?: string, origin?: string, sort?: string) => apiClient.community.listPosts(workId, origin, sort),
  getPost: (postId: string) => apiClient.community.getPost(postId),
  createPost: (payload: any) => apiClient.community.createPost(payload),
  updatePost: (postId: string, payload: any) => apiClient.community.updatePost(postId, payload),
  deletePost: (postId: string) => apiClient.community.deletePost(postId),
  listComments: (postId: string) => apiClient.community.listComments(postId),
  createComment: (postId: string, bodyMarkdown: string, parentCommentId?: string) => apiClient.community.createComment(postId, bodyMarkdown, parentCommentId),
  updateComment: (postId: string, commentId: string, payload: any) => apiClient.community.updateComment(postId, commentId, payload),
  deleteComment: (postId: string, commentId: string) => apiClient.community.deleteComment(postId, commentId),
  putReaction: (postId: string, liked: boolean, reactionType?: string) => apiClient.community.putReaction(postId, liked, reactionType),
  unlockContent: (contentType: 'POST' | 'COMMENT', contentId: string, versionNo?: number) => apiClient.community.unlockContent(contentType, contentId, versionNo),
  createCounterclaim: (postId: string, payload: any) => apiClient.community.createCounterclaim(postId, payload),
  reactToPost: (postId: string, reactionType: string) => apiClient.community.reactToPost(postId, reactionType)
};

export const magazineApi = {
  getArticles: (params?: any) => apiClient.magazine.listArticles(params),
  listArticles: (params?: any) => apiClient.magazine.listArticles(params),
  getArticle: (articleId: string) => apiClient.magazine.getArticle(articleId),
  getReactions: (articleId: string) => apiClient.magazine.getReactions(articleId),
  putReaction: (articleId: string, liked: boolean) => apiClient.magazine.putReaction(articleId, liked),
  getComments: (articleId: string) => apiClient.magazine.getComments(articleId),
  postComment: (articleId: string, bodyMarkdown: string, authorCutoffMs?: number, parentCommentId?: string | null) => apiClient.magazine.postComment(articleId, bodyMarkdown, authorCutoffMs, parentCommentId),
};

export const audienceLabApi = apiClient.audienceLab;
export const profileApi = apiClient.profile;
export const authApi = apiClient.auth;

export { ApiError };

