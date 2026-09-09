/**
 * Reframe V7 Film Detail Pure View-Model Transformation Module
 * Transforms raw API responses (FilmDTO, RevealSummaryDTO[], ProofCardDTO[])
 * into UI view-models for FilmHubPage while strictly preventing spoiler leakage,
 * hallucinated metrics, or fabricated timestamps.
 * Zero Paid Model Calls.
 */

export interface PersonEntity {
  qid?: string;
  name_en?: string;
  name_ko?: string;
  image?: string;
}

export interface FilmDetailViewModel {
  movieId: string;
  editionId?: string;
  runtimeMs?: number | null;
  title: string;
  titleKo?: string;
  year: string;
  runtimeDisplay: string;
  durationMins: number | null;
  ratingCode: string; // Empty string if not provided; NEVER defaulted to 'NR' in fixture OFF
  synopsis: string;   // Uses synopsis_safe only; NEVER falls back to raw synopsis
  posterPath?: string | null;
  director?: string;
  directors?: PersonEntity[];
  coreDemoSupported?: boolean;
  analysisStatus?: string;
  notice?: string;
  cast?: Array<{ name: string; role?: string; image?: string; imageSource?: string; imagePosition?: string; alt?: string; ariaLabel?: string; isPlaceholder?: boolean }>;
  genres?: string[];
  communityRatingAverage?: number | null;
  communityRatingCount?: number;
}

export interface RevealItemViewModel {
  revealId: string;
  title: string;
  safeTitle: string;
  timestampMs: number;
  timestampDisplay: string;
  spoilerCutoffMs: number;
  visibility: string;
  isLocked: boolean;
}

export interface ReframeCardViewModel {
  id: string; // Real proof_id, never array index or fallback
  scene: string;
  timestamp: string; // Formatted [HH:MM:SS] or empty
  title: string;
  body: string;
  likes?: number;
  comments?: number;
  hasSpoiler?: boolean;
  isLocked?: boolean;
  timestampMs?: number | null;
  spoilerCutoffMs?: number | null;
  movieId?: string | null;
  editionId?: string | null;
  sceneId?: string | null;
}

/**
 * Converts a finite non-negative millisecond value to [HH:MM:SS].
 * Returns empty string if invalid, negative, non-finite, or missing.
 */
export function formatTimestampMs(ms: unknown): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) {
    return '';
  }
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `[${pad(hours)}:${pad(minutes)}:${pad(seconds)}]`;
}

/**
 * Maps raw Film API response ({ data: FilmDTO } or FilmDTO) to FilmDetailViewModel.
 * Returns null if response is malformed.
 * Invariant:
 * - synopsis_safe only; if empty/missing, synopsis is empty (never falls back to raw synopsis).
 * - rating_code only if present; never defaults to 'NR'.
 */
export function mapFilmDtoToViewModel(raw: unknown): FilmDetailViewModel | null {
  if (!raw || typeof raw !== 'object') return null;

  const dto: any = ('data' in raw && (raw as any).data && typeof (raw as any).data === 'object')
    ? (raw as any).data
    : raw;

  if (typeof dto !== 'object' || dto === null) return null;

  const movieId = typeof dto.movie_id === 'string' && dto.movie_id.trim().length > 0
    ? dto.movie_id.trim()
    : '';

  const title = typeof dto.title === 'string' && dto.title.trim().length > 0
    ? dto.title.trim()
    : '';

  // Must have non-empty movie_id and title to be a valid film record
  if (!movieId || !title) {
    return null;
  }

  const durationMins = typeof dto.runtime_ms === 'number' && Number.isFinite(dto.runtime_ms) && dto.runtime_ms > 0
    ? Math.round(dto.runtime_ms / 60000)
    : (typeof dto.duration_mins === 'number' && Number.isFinite(dto.duration_mins) && dto.duration_mins > 0
      ? dto.duration_mins
      : null);

  const runtimeDisplay = durationMins !== null ? `${durationMins}min` : '';

  const year = dto.year != null && String(dto.year).trim() !== ''
    ? String(dto.year).trim()
    : (dto.release_year != null && String(dto.release_year).trim() !== '' ? String(dto.release_year).trim() : '');

  // rating_code: Empty string if missing; NEVER fabricate 'NR' in fixture OFF mode
  const ratingCode = typeof dto.rating_code === 'string' && dto.rating_code.trim().length > 0
    ? dto.rating_code.trim()
    : '';

  // synopsis: MUST use synopsis_safe ONLY.
  // If synopsis_safe is empty/null/missing, remains empty. NEVER falls back to raw synopsis.
  const synopsis = typeof dto.synopsis_safe === 'string'
    ? dto.synopsis_safe
    : '';

  const posterPath = typeof dto.poster_path === 'string' && dto.poster_path.startsWith('/assets/catalog/wikidata/')
    ? dto.poster_path
    : (movieId === 'the-bat-whispers-1930' ? '/assets/batwhispers-1-84-12615.png' : null);

  const titleKo = undefined;

  let directors: PersonEntity[] | undefined = undefined;
  let director: string | undefined = undefined;

  if (Array.isArray(dto.directors)) {
    const mappedDirectors = dto.directors
      .filter((d: any) => typeof d === 'object' && d !== null)
      .map((d: any) => ({
        qid: typeof d.qid === 'string' ? d.qid : undefined,
        name_en: typeof d.name_en === 'string' ? d.name_en : undefined,
        name_ko: typeof d.name_ko === 'string' ? d.name_ko : undefined,
        image: typeof d.image === 'string' ? d.image : typeof d.image_url === 'string' ? d.image_url : undefined,
      }));
    directors = mappedDirectors;
    const names = mappedDirectors
      .map((d: PersonEntity) => {
        if (d.name_en && d.name_en !== d.qid) return d.name_en;
        return d.name_en || d.qid || '';
      })
      .filter((n: string) => n.trim().length > 0);
    if (names.length > 0) {
      director = names.join(', ');
    }
  }

  if (!director && typeof dto.director === 'string' && dto.director.trim().length > 0) {
    director = dto.director.trim();
  }

  const coreDemoSupported = typeof dto.core_demo_supported === 'boolean'
    ? dto.core_demo_supported
    : (movieId === 'the-bat-whispers-1930');

  const analysisStatus = typeof dto.analysis_status === 'string'
    ? dto.analysis_status
    : (coreDemoSupported ? 'AVAILABLE' : 'NOT_SUPPORTED');

  const notice = typeof dto.analysis_notice === 'string'
    ? dto.analysis_notice
    : (typeof dto.notice === 'string'
        ? dto.notice
        : (!coreDemoSupported ? 'Core analysis features are currently available for demonstration on The Bat Whispers (1930) only.' : undefined));

  let castList: FilmDetailViewModel['cast'] = undefined;
  if (Array.isArray(dto.cast)) {
    castList = dto.cast.map((c: any) => {
      let name = '';
      if (typeof c === 'string') {
        name = c.trim();
      } else if (c && typeof c === 'object') {
        const en = typeof c.name_en === 'string' && c.name_en.trim().length > 0 ? c.name_en.trim() : null;
        const qid = typeof c.qid === 'string' && c.qid.trim().length > 0 ? c.qid.trim() : null;
        const fallback = typeof c.name === 'string' && c.name.trim().length > 0 ? c.name.trim() : null;
        name = (en && en !== qid ? en : fallback || qid || '');
      }

      // Do not invent roles if not present in source metadata
      const role = typeof c === 'object' && typeof c?.role === 'string' && c.role.trim().length > 0
        ? c.role.trim()
        : undefined;

      const image = typeof c === 'object' && typeof c?.image === 'string' && c.image.trim().length > 0
        ? c.image.trim()
        : undefined;

      return {
        name,
        role,
        image,
        imageSource: typeof c?.image_source === 'string' && c.image_source.startsWith('https://commons.wikimedia.org/wiki/File:') ? c.image_source : undefined,
        imagePosition: c?.image_position === 'right center' ? 'right center' : 'center top',
        alt: typeof c?.image_alt === 'string' ? c.image_alt : undefined,
        isPlaceholder: !Boolean(image),
      };
    }).filter((c: any) => c.name.trim().length > 0 && !/^Q\d+$/.test(c.name));
  }

  const directorEntries = (directors?.length ? directors.map(person => ({ name: person.name_en || '', role: 'Director', image: person.image, isPlaceholder: !person.image }))
    : director ? [{ name: director, role: 'Director', image: undefined, isPlaceholder: true }] : [])
    .filter(person => person.name && !/^Q\d+$/.test(person.name));
  castList = [...directorEntries, ...(castList || [])];

  let genres: string[] | undefined = undefined;
  if (Array.isArray(dto.genres)) {
    genres = dto.genres.map((g: any) => {
      if (typeof g === 'string') return g.trim();
      if (g && typeof g === 'object') {
        const en = typeof g.name_en === 'string' && g.name_en.trim().length > 0 ? g.name_en.trim() : null;
        const qid = typeof g.qid === 'string' && g.qid.trim().length > 0 ? g.qid.trim() : null;
        return (en && en !== qid ? en : qid || '');
      }
      return '';
    }).filter((g: string) => g.length > 0);
  }

  const ratingAverage = dto.average_rating ?? dto.community_rating_average;
  const ratingCount = dto.ratings_count ?? dto.community_rating_count;
  const communityRatingAverage = typeof ratingAverage === 'number' && Number.isFinite(ratingAverage)
    ? ratingAverage
    : null;
  const communityRatingCount = typeof ratingCount === 'number' && Number.isFinite(ratingCount)
    ? ratingCount
    : 0;

  const editionId = typeof dto.edition_id === 'string' && dto.edition_id.trim().length > 0
    ? dto.edition_id.trim()
    : undefined;

  const runtimeMs = typeof dto.runtime_ms === 'number' && Number.isFinite(dto.runtime_ms) && dto.runtime_ms > 0
    ? dto.runtime_ms
    : null;

  return {
    movieId,
    editionId,
    runtimeMs,
    title,
    titleKo,
    year,
    runtimeDisplay,
    durationMins,
    ratingCode,
    synopsis,
    posterPath,
    director,
    directors,
    coreDemoSupported,
    analysisStatus,
    notice,
    cast: castList,
    genres,
    communityRatingAverage,
    communityRatingCount,
  };
}

/**
 * Maps raw reveals API response ({ data: RevealSummaryDTO[] } or RevealSummaryDTO[])
 * to RevealItemViewModel[].
 * Returns null if response is malformed or if any reveal record has missing/empty reveal_id.
 * Invariants:
 * - reveal_id must be a non-empty string.
 * - visibility must be explicitly 'VISIBLE' with !is_locked to show raw title.
 * - LOCKED/MASKED/unknown visibility consumes structured safe_preview.title only; never falls back to raw title or safe_title.
 * - safeTitle view-model property NEVER falls back to raw title or safe_title in protected state.
 */
export function mapRevealsDtoToViewModel(raw: unknown): RevealItemViewModel[] | null {
  if (!raw || typeof raw !== 'object') return null;

  let list: any = null;
  if ('data' in raw && Array.isArray((raw as any).data)) {
    list = (raw as any).data;
  } else if ('reveals' in raw && Array.isArray((raw as any).reveals)) {
    list = (raw as any).reveals;
  } else if (Array.isArray(raw)) {
    list = raw;
  }

  if (!Array.isArray(list)) {
    return null;
  }

  const result: RevealItemViewModel[] = [];

  for (const r of list) {
    if (!r || typeof r !== 'object') return null;

    // reveal_id must be a non-empty string; never substituted with id or array index
    const revealId = typeof r.reveal_id === 'string' && r.reveal_id.trim().length > 0
      ? r.reveal_id.trim()
      : null;

    if (!revealId) {
      return null;
    }

    // Visibility rule: explicit VISIBLE and !is_locked required to show full payload.
    // Missing, undefined, or UNKNOWN visibility is NEVER assumed to be VISIBLE.
    const isExplicitlyVisible = r.visibility === 'VISIBLE' && !r.is_locked;
    const isLocked = !isExplicitlyVisible;

    let title = '';
    let safeTitle = '';

    if (isExplicitlyVisible) {
      title = typeof r.title === 'string' ? r.title : '';
      safeTitle = typeof r.safe_title === 'string' && r.safe_title.trim().length > 0
        ? r.safe_title.trim()
        : '';
    } else {
      // PROTECTED BRANCH:
      // Server safe_preview must be a validated { title, summary } object.
      // Do NOT tolerate strings, arrays, null, missing, or empty objects as valid preview.
      // Do NOT fall back to r.safe_title or r.title!
      const isValidSafePreviewObj =
        r.safe_preview &&
        typeof r.safe_preview === 'object' &&
        !Array.isArray(r.safe_preview);

      const previewTitle = (isValidSafePreviewObj && typeof r.safe_preview.title === 'string' && r.safe_preview.title.trim().length > 0)
        ? r.safe_preview.title.trim()
        : '';

      // Use ONLY structured safe_preview.title or neutral guidance
      title = previewTitle || 'Spoiler-protected reveal';
      safeTitle = previewTitle || 'Spoiler-protected reveal';
    }

    result.push({
      revealId,
      title: title.replace(/\s*\(\d{1,2}:\d{2}:\d{2}\)\s*$/, ''),
      safeTitle: safeTitle.replace(/\s*\(\d{1,2}:\d{2}:\d{2}\)\s*$/, ''),
      timestampMs: typeof r.timestamp_ms === 'number' && Number.isFinite(r.timestamp_ms) && r.timestamp_ms >= 0 ? r.timestamp_ms : 0,
      timestampDisplay: formatTimestampMs(r.timestamp_ms),
      spoilerCutoffMs: typeof r.spoiler_cutoff_ms === 'number' && Number.isFinite(r.spoiler_cutoff_ms) && r.spoiler_cutoff_ms >= 0 ? r.spoiler_cutoff_ms : 0,
      visibility: typeof r.visibility === 'string' ? r.visibility : 'UNKNOWN',
      isLocked,
    });
  }

  return result;
}

/**
 * Maps raw proof API response ({ data: ProofCardDTO[] } or ProofCardDTO[])
 * to ReframeCardViewModel[].
 * Strictly enforces:
 * - Real proof_id identity (never substituted with moment_id/id/array index)
 * - If proof_id is missing or empty string, returns null (error state)
 * - Strict separation of PUBLIC vs PROTECTED branches:
 *   - PROTECTED branch (LOCKED/MASKED/UNKNOWN/is_locked):
 *     - Zero access to raw timestamp_ms, reframed_timestamp_ms, evidence_chain, observed_premises
 *     - Timestamp is strictly empty string ""
 *     - Zero access to raw scene or scene_number; safe scene_id is preserved if present
 *     - safe_preview must be structured { title, summary } object; strings/null fall back to neutral guidance
 *   - PUBLIC branch:
 *     - Normal formatted time, scene label, and body
 * - True presence of metrics (never synthesized like/comment counts)
 * Returns null if response is malformed.
 */
export function mapProofsDtoToReframeCards(raw: unknown): ReframeCardViewModel[] | null {
  if (!raw || typeof raw !== 'object') return null;

  let list: any = null;
  if ('data' in raw && Array.isArray((raw as any).data)) {
    list = (raw as any).data;
  } else if ('reframed_moments' in raw && Array.isArray((raw as any).reframed_moments)) {
    list = (raw as any).reframed_moments;
  } else if ('moments' in raw && Array.isArray((raw as any).moments)) {
    list = (raw as any).moments;
  } else if (Array.isArray(raw)) {
    list = raw;
  }

  if (!Array.isArray(list)) {
    return null;
  }

  const cards: ReframeCardViewModel[] = [];

  for (const p of list) {
    if (!p || typeof p !== 'object') return null;

    // proof_id must be a non-empty string.
    // NEVER substitute with moment_id, id, or array index!
    const proofId = typeof p.proof_id === 'string' && p.proof_id.trim().length > 0
      ? p.proof_id.trim()
      : null;

    if (!proofId) {
      // Invalid record: error according to requirement A.3
      return null;
    }

    // Visibility rule: explicit VISIBLE and !is_locked required to show full payload.
    // Missing, null, or UNKNOWN visibility is NEVER assumed to be VISIBLE.
    const isExplicitlyVisible = p.visibility === 'VISIBLE' && !p.is_locked;
    const isLocked = !isExplicitlyVisible;

    let title = '';
    let body = '';
    let scene = '';
    let timestamp = '';
    let rawMs: number | null = null;

    if (isExplicitlyVisible) {
      // ----------------------------------------------------------------------
      // PUBLIC BRANCH: Full payload permitted
      // ----------------------------------------------------------------------
      title = typeof p.title === 'string'
        ? p.title
        : (typeof p.name === 'string' ? p.name : '');

      body = typeof p.blind_explanation === 'string' && p.blind_explanation.trim().length > 0
        ? p.blind_explanation
        : (typeof p.reveal_explanation === 'string'
          ? p.reveal_explanation
          : (typeof p.body === 'string'
            ? p.body
            : (typeof p.summary === 'string'
              ? p.summary
              : (typeof p.explanation === 'string' ? p.explanation : ''))));

      // Timestamp ms resolution for public cards
      rawMs = (typeof p.timestamp_ms === 'number' && Number.isFinite(p.timestamp_ms) && p.timestamp_ms >= 0)
        ? p.timestamp_ms
        : (typeof p.reframed_timestamp_ms === 'number' && Number.isFinite(p.reframed_timestamp_ms) && p.reframed_timestamp_ms >= 0
          ? p.reframed_timestamp_ms
          : (typeof p.evidence_chain?.[0]?.timestamp_ms === 'number' && Number.isFinite(p.evidence_chain[0].timestamp_ms) && p.evidence_chain[0].timestamp_ms >= 0
            ? p.evidence_chain[0].timestamp_ms
            : (typeof p.observed_premises?.[0]?.timestamp_ms === 'number' && Number.isFinite(p.observed_premises[0].timestamp_ms) && p.observed_premises[0].timestamp_ms >= 0
              ? p.observed_premises[0].timestamp_ms
              : null)));

      timestamp = formatTimestampMs(rawMs);

      // Scene label resolution for public cards
      if (typeof p.scene === 'string' && p.scene.trim().length > 0) {
        scene = p.scene.trim();
      } else if (p.scene_number != null) {
        scene = `SCENE ${p.scene_number}`;
      } else if (typeof p.scene_id === 'string' && p.scene_id.trim().length > 0) {
        scene = p.scene_id.trim();
      }
    } else {
      // ----------------------------------------------------------------------
      // PROTECTED BRANCH: (LOCKED / MASKED / UNKNOWN / missing visibility / is_locked = true)
      // Strictly aligned with sanitize_payload_for_viewer allowlist:
      // - NO raw scene, scene_number, timestamp_ms, reframed_timestamp_ms, evidence_chain, observed_premises
      // - Timestamp MUST be empty string (no allowed timestamp in protected contract)
      // - Safe scene_id is preserved if present
      // - safe_preview MUST be a structured { title, summary } object. Missing/string/array -> neutral guidance
      // ----------------------------------------------------------------------
      const isValidSafePreviewObj =
        p.safe_preview &&
        typeof p.safe_preview === 'object' &&
        !Array.isArray(p.safe_preview);

      const previewTitle = (isValidSafePreviewObj && typeof p.safe_preview.title === 'string' && p.safe_preview.title.trim().length > 0)
        ? p.safe_preview.title.trim()
        : '';

      const previewSummary = (isValidSafePreviewObj && typeof p.safe_preview.summary === 'string' && p.safe_preview.summary.trim().length > 0)
        ? p.safe_preview.summary.trim()
        : (isValidSafePreviewObj && typeof p.safe_preview.body === 'string' && p.safe_preview.body.trim().length > 0
          ? p.safe_preview.body.trim()
          : '');

      title = previewTitle || 'Spoiler-protected content';
      body = previewSummary || 'Content hidden behind spoiler protection. Complete the required reveal to unlock.';

      // Timestamp is strictly empty for protected cards; do NOT inspect raw timestamps or evidence getters
      timestamp = '';

      // Scene: only safe scene_id is permitted from allowlist; raw scene/scene_number are strictly omitted
      if (typeof p.scene_id === 'string' && p.scene_id.trim().length > 0) {
        scene = p.scene_id.trim();
      } else {
        scene = '';
      }
    }

    // Likes & comments (permitted in both public and protected allowlists)
    const likes = typeof p.likes === 'number' && Number.isFinite(p.likes)
      ? p.likes
      : (typeof p.reaction_counts?.LIKE === 'number' && Number.isFinite(p.reaction_counts.LIKE) ? p.reaction_counts.LIKE : undefined);

    const comments = typeof p.comments === 'number' && Number.isFinite(p.comments)
      ? p.comments
      : (typeof p.reply_count === 'number' && Number.isFinite(p.reply_count) ? p.reply_count : undefined);

    const cardTimestampMs = isExplicitlyVisible && typeof rawMs === 'number' ? rawMs : null;
    const cardSceneId = typeof p.scene_id === 'string' ? p.scene_id : null;

    const spoilerCutoffMs = (typeof p.spoiler_cutoff_ms === 'number' && Number.isFinite(p.spoiler_cutoff_ms) && p.spoiler_cutoff_ms >= 0)
      ? p.spoiler_cutoff_ms
      : (typeof p.cutoff_ms === 'number' && Number.isFinite(p.cutoff_ms) && p.cutoff_ms >= 0
        ? p.cutoff_ms
        : (typeof p.unlock_metadata?.minimum_progress_ms === 'number' && Number.isFinite(p.unlock_metadata.minimum_progress_ms) && p.unlock_metadata.minimum_progress_ms >= 0
          ? p.unlock_metadata.minimum_progress_ms
          : null));

    const cardMovieId = (typeof p.movie_id === 'string' && p.movie_id.trim().length > 0)
      ? p.movie_id.trim()
      : (typeof p.work_id === 'string' && p.work_id.trim().length > 0 ? p.work_id.trim() : null);
    const cardEditionId = typeof p.edition_id === 'string' && p.edition_id.trim().length > 0 ? p.edition_id.trim() : null;

    cards.push({
      id: proofId,
      scene,
      timestamp,
      title,
      body,
      likes,
      comments,
      hasSpoiler: isLocked || Boolean(p.has_spoiler || p.is_spoiler),
      isLocked,
      timestampMs: cardTimestampMs,
      spoilerCutoffMs,
      movieId: cardMovieId,
      editionId: cardEditionId,
      sceneId: cardSceneId,
    });
  }

  return cards;
}
