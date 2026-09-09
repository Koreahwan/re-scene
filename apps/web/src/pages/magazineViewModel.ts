/**
 * Reframe V7 Pure Magazine View-Model Mapper
 * Strictly validates responses from GET /api/v1/magazine and GET /api/v1/magazine/{article_id}.
 * 
 * Epistemic & Security Invariants:
 * - List envelope is strictly { articles: [...], total: number, disclaimer?: string } (NOT { data: [...] }).
 * - Detail envelope is the article record itself + body_sections + evidence_refs (NOT { data: ... }).
 * - article_id must be a valid UUID string.
 * - Only is_spoiler_locked === false permits reading raw body sections and evidence references.
 * - is_spoiler_locked !== false (true, missing, wrong type) is PROTECTED:
 *   never accesses, copies, or stores body_sections or evidence_refs.
 * - Known body sections are separated into epistemic tiers:
 *   Observable facts (WHAT_THE_FILM_SHOWS, CANONICAL_METADATA),
 *   Engine inference (ENGINE_INTERPRETATION, REWATCH_TIMESTAMPS),
 *   Synthetic views (SYNTHETIC_AUTHOR_VIEW, ALTERNATIVE_EXPLANATION).
 *   Never promoted to "VERIFIED_CANON".
 * - Honest disclosure: is_synthetic, content_origin, generator_mode, ai_disclosure, trust_class.
 * - No inventing absent optional information: missing fields stay null / omitted.
 * Zero Paid Model Calls.
 */

import { rankingFields, RankingFields } from '../utils/contentRanking';

export interface MagazineCardViewModel extends RankingFields {
  articleId: string;
  title: string;
  dek: string | null;
  articleType: string | null;
  workId: string | null;
  authorAlias: string | null;
  isSynthetic: boolean | null;
  contentOrigin: string | null;
  generatorMode: string | null;
  aiDisclosure: string | null;
  trustClass: string | null;
  spoilerCutoffMs: number | null;
  isSpoilerLocked: boolean;
  publishedAt: string | null;
  publishedAtFormatted: string | null;
  heroImage: string | null;
}

export type MagazineListResult =
  | { kind: 'EMPTY'; total: number; disclaimer: string | null }
  | { kind: 'ERROR'; error: string }
  | { kind: 'SUCCESS'; articles: MagazineCardViewModel[]; total: number; disclaimer: string | null };

export interface EvidenceRefViewModel {
  evidenceId: string;
  evidenceType: string | null;
  evidenceHash: string | null;
  timestampMs: number | null;
  timestampFormatted: string | null;
  trustClass: string | null;
}

export interface BodySectionViewModel {
  key: string;
  tier: 'OBSERVED_FACT' | 'ENGINE_INFERENCE' | 'SYNTHETIC_EDITORIAL';
  title: string;
  content: string;
}

export interface VisibleMagazineArticleViewModel {
  kind: 'VISIBLE';
  articleId: string;
  title: string;
  dek: string | null;
  articleType: string | null;
  workId: string | null;
  authorAlias: string | null;
  isSynthetic: boolean | null;
  contentOrigin: string | null;
  generatorMode: string | null;
  aiDisclosure: string | null;
  trustClass: string | null;
  spoilerCutoffMs: number | null;
  isSpoilerLocked: false;
  publishedAt?: string | null;
  publishedAtFormatted?: string | null;
  heroImage?: string | null;
  introParagraphs?: string[];
  paragraphs?: string[];
  outroParagraphs?: string[];
  readTimeMinutes?: number | null;
  bodySections: BodySectionViewModel[];
  evidenceRefs: EvidenceRefViewModel[];
}

export interface ProtectedMagazineArticleViewModel {
  kind: 'PROTECTED';
  articleId: string;
  title: string;
  dek: string | null;
  articleType: string | null;
  workId: string | null;
  authorAlias: string | null;
  isSynthetic: boolean | null;
  contentOrigin: string | null;
  generatorMode: string | null;
  aiDisclosure: string | null;
  trustClass: string | null;
  spoilerCutoffMs: number | null;
  isSpoilerLocked: true;
}

export type MagazineDetailResult =
  | { kind: 'ERROR'; error: string; statusCode?: number }
  | { kind: 'PROTECTED'; article: ProtectedMagazineArticleViewModel }
  | { kind: 'VISIBLE'; article: VisibleMagazineArticleViewModel };

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isValidUuid(id: string): boolean {
  if (typeof id !== 'string') return false;
  return UUID_REGEX.test(id.trim());
}

const KNOWN_BODY_SECTIONS: Record<
  string,
  { title: string; tier: 'OBSERVED_FACT' | 'ENGINE_INFERENCE' | 'SYNTHETIC_EDITORIAL' }
> = {
  WHAT_THE_FILM_SHOWS: {
    title: 'Observed Cinematic Scenes (Factual Evidence)',
    tier: 'OBSERVED_FACT',
  },
  CANONICAL_METADATA: {
    title: 'Canonical Metadata',
    tier: 'OBSERVED_FACT',
  },
  ENGINE_INTERPRETATION: {
    title: 'Engine Analysis (Narrative Inference)',
    tier: 'ENGINE_INFERENCE',
  },
  REWATCH_TIMESTAMPS: {
    title: 'Rewatch Timestamps and Evidence Grounding',
    tier: 'ENGINE_INFERENCE',
  },
  SYNTHETIC_AUTHOR_VIEW: {
    title: 'Synthetic Editorial Perspective',
    tier: 'SYNTHETIC_EDITORIAL',
  },
  ALTERNATIVE_EXPLANATION: {
    title: 'Alternative Narrative Interpretation',
    tier: 'SYNTHETIC_EDITORIAL',
  },
};

/**
 * Pure mapper for GET /api/v1/magazine?work_id=the-bat-whispers-1930
 * Envelope: { articles: [...], total: number, disclaimer?: string }
 */
export function parseMagazineListResponse(raw: unknown): MagazineListResult {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {
      kind: 'ERROR',
      error: 'Malformed magazine list response: expected an object envelope',
    };
  }

  const rawObj = raw as Record<string, unknown>;

  if (!('articles' in rawObj) || !Array.isArray(rawObj.articles)) {
    return {
      kind: 'ERROR',
      error: 'Malformed magazine list response: missing or non-array "articles"',
    };
  }

  // total must be a finite non-negative integer
  if (
    typeof rawObj.total !== 'number' ||
    !Number.isFinite(rawObj.total) ||
    !Number.isInteger(rawObj.total) ||
    rawObj.total < 0
  ) {
    return {
      kind: 'ERROR',
      error: 'Malformed magazine list response: total must be a finite non-negative integer',
    };
  }

  const total = rawObj.total;
  const disclaimer =
    typeof rawObj.disclaimer === 'string' && rawObj.disclaimer.trim()
      ? rawObj.disclaimer.trim()
      : null;

  if (rawObj.articles.length === 0) {
    return { kind: 'EMPTY', total, disclaimer };
  }

  const articles: MagazineCardViewModel[] = [];

  for (let i = 0; i < rawObj.articles.length; i++) {
    const item = rawObj.articles[i];
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return {
        kind: 'ERROR',
        error: `Malformed article record at index ${i}: expected an object`,
      };
    }

    const rec = item as Record<string, unknown>;

    // article_id must be non-empty string and valid UUID
    if (
      !('article_id' in rec) ||
      typeof rec.article_id !== 'string' ||
      !rec.article_id.trim()
    ) {
      return {
        kind: 'ERROR',
        error: `Malformed article record at index ${i}: missing or empty article_id`,
      };
    }

    const articleId = rec.article_id.trim();
    if (!isValidUuid(articleId)) {
      return {
        kind: 'ERROR',
        error: `Malformed article record at index ${i}: article_id "${articleId}" is not a valid UUID`,
      };
    }

    // title must be non-empty string
    if (!('title' in rec) || typeof rec.title !== 'string' || !rec.title.trim()) {
      return {
        kind: 'ERROR',
        error: `Malformed article record at index ${i}: missing or empty title`,
      };
    }
    const title = rec.title.trim();

    const dek =
      typeof rec.dek === 'string' && rec.dek.trim() ? rec.dek.trim() : null;

    const articleType =
      typeof rec.article_type === 'string' && rec.article_type.trim()
        ? rec.article_type.trim()
        : null;

    const workId =
      typeof rec.work_id === 'string' && rec.work_id.trim()
        ? rec.work_id.trim()
        : null;

    const authorAlias =
      typeof rec.author_alias === 'string' && rec.author_alias.trim()
        ? rec.author_alias.trim()
        : null;

    // Strict boolean only. Missing or wrong type -> null.
    const isSynthetic =
      typeof rec.is_synthetic === 'boolean' ? rec.is_synthetic : null;

    const contentOrigin =
      typeof rec.content_origin === 'string' && rec.content_origin.trim()
        ? rec.content_origin.trim()
        : null;

    const generatorMode =
      typeof rec.generator_mode === 'string' && rec.generator_mode.trim()
        ? rec.generator_mode.trim()
        : null;

    const aiDisclosure =
      typeof rec.ai_disclosure === 'string' && rec.ai_disclosure.trim()
        ? rec.ai_disclosure.trim()
        : null;

    const trustClass =
      typeof rec.trust_class === 'string' && rec.trust_class.trim()
        ? rec.trust_class.trim()
        : null;

    const spoilerCutoffMs =
      typeof rec.spoiler_cutoff_ms === 'number' &&
      Number.isFinite(rec.spoiler_cutoff_ms) &&
      rec.spoiler_cutoff_ms >= 0
        ? rec.spoiler_cutoff_ms
        : null;

    // Strict lock evaluation: ONLY exact boolean false is unlocked.
    // Missing, null, 0, '', 'false', or other wrong type is protected (true).
    const isSpoilerLocked = rec.is_spoiler_locked !== false;

    const publishedAt =
      typeof rec.published_at === 'string' && rec.published_at.trim()
        ? rec.published_at.trim()
        : null;

    let publishedAtFormatted: string | null = null;
    if (publishedAt) {
      const d = new Date(publishedAt);
      if (!isNaN(d.getTime())) {
        const yr = d.getUTCFullYear();
        const mo = String(d.getUTCMonth() + 1).padStart(2, '0');
        const day = String(d.getUTCDate()).padStart(2, '0');
        publishedAtFormatted = `${yr}.${mo}.${day}`;
      }
    }

    const heroImage =
      typeof rec.hero_image_url === 'string' && rec.hero_image_url.trim()
        ? rec.hero_image_url.trim()
        : typeof rec.thumbnail_url === 'string' && rec.thumbnail_url.trim()
        ? rec.thumbnail_url.trim()
        : typeof rec.hero_image === 'string' && rec.hero_image.trim()
        ? rec.hero_image.trim()
        : null;

    articles.push({
      ...rankingFields({ ...rec, registered_at: rec.registered_at ?? rec.published_at }),
      articleId,
      title,
      dek,
      articleType,
      workId,
      authorAlias,
      isSynthetic,
      contentOrigin,
      generatorMode,
      aiDisclosure,
      trustClass,
      spoilerCutoffMs,
      isSpoilerLocked,
      publishedAt,
      publishedAtFormatted,
      heroImage,
    });
  }

  return { kind: 'SUCCESS', articles, total, disclaimer };
}

/**
 * Pure mapper for GET /api/v1/magazine/{article_id}
 * Expects the article record directly with body_sections and evidence_refs.
 */
export function parseMagazineDetailResponse(
  raw: unknown,
  expectedArticleId: string
): MagazineDetailResult {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {
      kind: 'ERROR',
      error: 'Malformed magazine detail response: expected an object',
    };
  }

  const rec = raw as Record<string, unknown>;

  // article_id must be non-empty string and match expected
  if (
    !('article_id' in rec) ||
    typeof rec.article_id !== 'string' ||
    !rec.article_id.trim()
  ) {
    return {
      kind: 'ERROR',
      error: 'Malformed magazine detail record: missing or empty article_id',
    };
  }

  const articleId = rec.article_id.trim();
  if (articleId.toLowerCase() !== expectedArticleId.trim().toLowerCase()) {
    return {
      kind: 'ERROR',
      error: `Mismatched article_id: expected "${expectedArticleId}", got "${articleId}"`,
    };
  }

  if (!isValidUuid(articleId)) {
    return {
      kind: 'ERROR',
      error: `Invalid article_id UUID format: "${articleId}"`,
    };
  }

  // title must be non-empty string
  if (!('title' in rec) || typeof rec.title !== 'string' || !rec.title.trim()) {
    return {
      kind: 'ERROR',
      error: 'Malformed magazine detail record: missing or empty title',
    };
  }
  const title = rec.title.trim();

  // Check spoiler lock condition:
  // ONLY exact boolean false allows reading body_sections and evidence_refs!
  const isLocked = rec.is_spoiler_locked !== false;

  const workId =
    typeof rec.work_id === 'string' && rec.work_id.trim()
      ? rec.work_id.trim()
      : null;

  const articleType =
    typeof rec.article_type === 'string' && rec.article_type.trim()
      ? rec.article_type.trim()
      : null;

  const authorAlias =
    typeof rec.author_alias === 'string' && rec.author_alias.trim()
      ? rec.author_alias.trim()
      : null;

  const isSynthetic =
    typeof rec.is_synthetic === 'boolean' ? rec.is_synthetic : null;

  const contentOrigin =
    typeof rec.content_origin === 'string' && rec.content_origin.trim()
      ? rec.content_origin.trim()
      : null;

  const generatorMode =
    typeof rec.generator_mode === 'string' && rec.generator_mode.trim()
      ? rec.generator_mode.trim()
      : null;

  const aiDisclosure =
    typeof rec.ai_disclosure === 'string' && rec.ai_disclosure.trim()
      ? rec.ai_disclosure.trim()
      : null;

  const trustClass =
    typeof rec.trust_class === 'string' && rec.trust_class.trim()
      ? rec.trust_class.trim()
      : null;

  const spoilerCutoffMs =
    typeof rec.spoiler_cutoff_ms === 'number' &&
    Number.isFinite(rec.spoiler_cutoff_ms) &&
    rec.spoiler_cutoff_ms >= 0
      ? rec.spoiler_cutoff_ms
      : null;

  const dek =
    typeof rec.dek === 'string' && rec.dek.trim() ? rec.dek.trim() : null;

  // --------------------------------------------------------------------------
  // PROTECTED BRANCH
  // (is_spoiler_locked is true, null, undefined, or not boolean false)
  // NEVER read, access, or store body_sections or evidence_refs.
  // --------------------------------------------------------------------------
  if (isLocked) {
    return {
      kind: 'PROTECTED',
      article: {
        kind: 'PROTECTED',
        articleId,
        title,
        dek,
        articleType,
        workId,
        authorAlias,
        isSynthetic,
        contentOrigin,
        generatorMode,
        aiDisclosure,
        trustClass,
        spoilerCutoffMs,
        isSpoilerLocked: true,
      },
    };
  }

  // --------------------------------------------------------------------------
  // VISIBLE BRANCH
  // (is_spoiler_locked === false)
  // Safely parse body_sections and evidence_refs.
  // --------------------------------------------------------------------------
  const bodySections: BodySectionViewModel[] = [];
  if (
    rec.body_sections &&
    typeof rec.body_sections === 'object' &&
    !Array.isArray(rec.body_sections)
  ) {
    const sectionsObj = rec.body_sections as Record<string, unknown>;

    for (const [key, meta] of Object.entries(KNOWN_BODY_SECTIONS)) {
      if (key in sectionsObj) {
        const val = sectionsObj[key];
        // ONLY valid non-empty string is displayed. Object, array, number, boolean are omitted.
        // No JSON.stringify or String fallback!
        if (typeof val === 'string' && val.trim()) {
          bodySections.push({
            key,
            tier: meta.tier,
            title: meta.title,
            content: val.trim(),
          });
        }
      }
    }
  }

  const evidenceRefs: EvidenceRefViewModel[] = [];
  if (Array.isArray(rec.evidence_refs)) {
    for (let i = 0; i < rec.evidence_refs.length; i++) {
      const item = rec.evidence_refs[i];
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        continue;
      }
      const ev = item as Record<string, unknown>;

      const evidenceId =
        typeof ev.evidence_id === 'string' && ev.evidence_id.trim()
          ? ev.evidence_id.trim()
          : null;
      if (!evidenceId) {
        continue;
      }

      let timestampMs: number | null = null;
      if ('timestamp_ms' in ev && ev.timestamp_ms !== null && ev.timestamp_ms !== undefined) {
        if (typeof ev.timestamp_ms !== 'number' || !Number.isFinite(ev.timestamp_ms) || ev.timestamp_ms < 0) {
          continue; // skip items with invalid timestamp shape
        }
        timestampMs = ev.timestamp_ms;
      }

      const evidenceType =
        typeof ev.evidence_type === 'string' && ev.evidence_type.trim()
          ? ev.evidence_type.trim()
          : typeof ev.type === 'string' && ev.type.trim()
          ? ev.type.trim()
          : null;

      const evidenceHash =
        typeof ev.evidence_hash === 'string' && ev.evidence_hash.trim()
          ? ev.evidence_hash.trim()
          : typeof ev.hash === 'string' && ev.hash.trim()
          ? ev.hash.trim()
          : null;

      const timestampFormatted =
        timestampMs !== null ? `${(timestampMs / 1000).toFixed(1)}s` : null;

      const trustClassVal =
        typeof ev.trust_class === 'string' && ev.trust_class.trim()
          ? ev.trust_class.trim()
          : null;

      evidenceRefs.push({
        evidenceId,
        evidenceType,
        evidenceHash,
        timestampMs,
        timestampFormatted,
        trustClass: trustClassVal,
      });
    }
  }

  const publishedAt =
    typeof rec.published_at === 'string' && rec.published_at.trim()
      ? rec.published_at.trim()
      : null;

  let publishedAtFormatted: string | null = null;
  if (publishedAt) {
    const d = new Date(publishedAt);
    if (!isNaN(d.getTime())) {
      const yr = d.getUTCFullYear();
      const mo = String(d.getUTCMonth() + 1).padStart(2, '0');
      const day = String(d.getUTCDate()).padStart(2, '0');
      publishedAtFormatted = `${yr}.${mo}.${day}`;
    }
  }

  const heroImage =
    typeof rec.hero_image_url === 'string' && rec.hero_image_url.trim()
      ? rec.hero_image_url.trim()
      : null;

  const introParagraphs = Array.isArray(rec.intro_paragraphs)
    ? rec.intro_paragraphs.filter((p): p is string => typeof p === 'string' && p.trim().length > 0)
    : [];

  const paragraphs = Array.isArray(rec.paragraphs)
    ? rec.paragraphs.filter((p): p is string => typeof p === 'string' && p.trim().length > 0)
    : [];

  const outroParagraphs = Array.isArray(rec.outro_paragraphs)
    ? rec.outro_paragraphs.filter((p): p is string => typeof p === 'string' && p.trim().length > 0)
    : [];

  const readTimeMinutes =
    typeof rec.read_time_minutes === 'number' && Number.isFinite(rec.read_time_minutes)
      ? rec.read_time_minutes
      : null;

  return {
    kind: 'VISIBLE',
    article: {
      kind: 'VISIBLE',
      articleId,
      title,
      dek,
      articleType,
      workId,
      authorAlias,
      isSynthetic,
      contentOrigin,
      generatorMode,
      aiDisclosure,
      trustClass,
      spoilerCutoffMs,
      isSpoilerLocked: false,
      publishedAt,
      publishedAtFormatted,
      heroImage,
      introParagraphs,
      paragraphs,
      outroParagraphs,
      readTimeMinutes,
      bodySections,
      evidenceRefs,
    },
  };
}
