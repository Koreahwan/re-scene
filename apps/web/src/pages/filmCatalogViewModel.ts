/**
 * Reframe V7 Pure Film Catalog View-Model Mapper & Search Filter
 * Implements strict response validation for GET /api/v1/films { data: FilmSummary[], meta: { total: 1 } }.
 * Ensures:
 * - Malformed envelopes and records produce explicit error results, never disguised as empty successes.
 * - movie_id and title are strictly required non-empty strings on every record; missing/null/whitespace/wrong types fail the entire parse.
 * - Mixed valid + invalid lists fail closed with success: false.
 * - Only valid { data: [] } produces success: true with empty films.
 * - No array index or legacy id fallback for movie_id fabrication.
 * - Local poster path is strictly isolated to 'the-bat-whispers-1930'; other films receive null (no external calls).
 * - Safe title-based substring filtering with whitespace trimming and case-insensitivity.
 * Zero Paid Model Calls.
 */

export interface PersonEntity {
  qid?: string;
  name_en?: string;
  name_ko?: string;
}

export interface GenreEntity {
  qid?: string;
  name_en?: string;
  name_ko?: string;
}

import { rankingFields, RankingFields } from '../utils/contentRanking';

export interface FilmCatalogItemViewModel extends RankingFields {
  movieId: string;
  title: string;
  titleKo?: string;
  year?: number | string;
  posterPath: string | null;
  destination: string;
  director?: string;
  directors?: PersonEntity[];
  genres?: GenreEntity[];
  coreDemoSupported?: boolean;
}

export function extractEntityName(item: unknown, preferKo = false): string {
  if (typeof item === 'string') return item.trim();
  if (item && typeof item === 'object') {
    const obj = item as Record<string, unknown>;
    const ko = typeof obj.name_ko === 'string' && obj.name_ko.trim().length > 0 ? obj.name_ko.trim() : null;
    const en = typeof obj.name_en === 'string' && obj.name_en.trim().length > 0 ? obj.name_en.trim() : null;
    const qid = typeof obj.qid === 'string' && obj.qid.trim().length > 0 ? obj.qid.trim() : null;
    if (preferKo && ko) return ko;
    if (en && en !== qid) return en;
    return en || ko || qid || '';
  }
  return '';
}

export type FilmCatalogParseResult =
  | { success: true; films: FilmCatalogItemViewModel[] }
  | { success: false; error: string };

const BAT_WHISPERS_LOCAL_POSTER =
  '/assets/catalog/wikidata/Q3985804-english-b7da81ff.jpg';

/**
 * Validates and maps raw API catalog response to FilmCatalogItemViewModel array.
 * Fails closed on malformed envelope or malformed records.
 */
export function mapFilmCatalogResponse(raw: unknown): FilmCatalogParseResult {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {
      success: false,
      error: 'Malformed catalog response: payload must be an object',
    };
  }

  const rawObj = raw as Record<string, unknown>;
  if (!('data' in rawObj) || !Array.isArray(rawObj.data)) {
    return {
      success: false,
      error: 'Malformed catalog response: missing or invalid "data" array',
    };
  }

  const rawList = rawObj.data as unknown[];
  const validFilms: FilmCatalogItemViewModel[] = [];

  for (let i = 0; i < rawList.length; i++) {
    const item = rawList[i];
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return {
        success: false,
        error: `Malformed catalog record at index ${i}: record must be an object`,
      };
    }

    const record = item as Record<string, unknown>;

    // movie_id is strictly required: must be string, non-empty when trimmed
    if (
      !('movie_id' in record) ||
      record.movie_id === null ||
      record.movie_id === undefined ||
      typeof record.movie_id !== 'string' ||
      record.movie_id.trim() === ''
    ) {
      return {
        success: false,
        error: `Malformed catalog record at index ${i}: movie_id must be a non-empty string`,
      };
    }

    // title is strictly required: must be string, non-empty when trimmed
    if (
      !('title' in record) ||
      record.title === null ||
      record.title === undefined ||
      typeof record.title !== 'string' ||
      record.title.trim() === ''
    ) {
      return {
        success: false,
        error: `Malformed catalog record at index ${i}: title must be a non-empty string`,
      };
    }

    const trimmedMovieId = record.movie_id.trim();
    const trimmedTitle = record.title.trim();

    // Poster assignment: ONLY 'the-bat-whispers-1930' receives the known local poster,
    // or safe same-origin /assets/catalog/wikidata/... paths.
    // Untrusted external URLs or missing posters receive null (clean placeholder).
    let posterPath: string | null = null;
    if (trimmedMovieId === 'the-bat-whispers-1930') {
      posterPath = BAT_WHISPERS_LOCAL_POSTER;
    } else if (
      typeof record.poster_path === 'string' &&
      record.poster_path.startsWith('/assets/catalog/wikidata/')
    ) {
      posterPath = record.poster_path;
    }

    const titleKo =
      typeof record.title_ko === 'string' && record.title_ko.trim().length > 0
        ? record.title_ko.trim()
        : undefined;

    let directors: PersonEntity[] | undefined = undefined;
    let director: string | undefined = undefined;

    if (Array.isArray(record.directors)) {
      directors = record.directors
        .filter((d): d is PersonEntity => typeof d === 'object' && d !== null)
        .map((d) => ({
          qid: typeof d.qid === 'string' ? d.qid : undefined,
          name_en: typeof d.name_en === 'string' ? d.name_en : undefined,
          name_ko: typeof d.name_ko === 'string' ? d.name_ko : undefined,
        }));
      const names = directors.map((d) => extractEntityName(d)).filter((n) => n.length > 0);
      if (names.length > 0) {
        director = names.join(', ');
      }
    }

    if (!director && typeof record.director === 'string' && record.director.trim().length > 0) {
      director = record.director.trim();
    }

    const coreDemoSupported =
      typeof record.core_demo_supported === 'boolean'
        ? record.core_demo_supported
        : trimmedMovieId === 'the-bat-whispers-1930';

    let genres: GenreEntity[] | undefined = undefined;
    if (Array.isArray(record.genres)) {
      genres = record.genres
        .filter((g): g is Record<string, unknown> => typeof g === 'object' && g !== null)
        .map((g) => ({
          qid: typeof g.qid === 'string' ? g.qid : undefined,
          name_en: typeof g.name_en === 'string' ? g.name_en : undefined,
          name_ko: typeof g.name_ko === 'string' ? g.name_ko : undefined,
        }));
    }

    validFilms.push({
      ...rankingFields(record),
      movieId: trimmedMovieId,
      title: trimmedTitle,
      titleKo,
      year: typeof record.year === 'number' || typeof record.year === 'string' ? record.year : undefined,
      posterPath,
      destination: `/films/${encodeURIComponent(trimmedMovieId)}`,
      director,
      directors,
      genres,
      coreDemoSupported,
    });
  }

  return {
    success: true,
    films: validFilms,
  };
}

/**
 * Pure client-side title filter with case-insensitivity, whitespace trimming,
 * and safe handling of missing/undefined properties and special characters.
 * Matches both English title and Korean title (titleKo).
 */
export function filterFilmsByQuery(
  films: FilmCatalogItemViewModel[],
  query?: string | null
): FilmCatalogItemViewModel[] {
  if (!query) {
    return films;
  }
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return films;
  }

  return films.filter((film) => {
    const titleEn = typeof film?.title === 'string' ? film.title.toLowerCase() : '';
    const titleKo = typeof film?.titleKo === 'string' ? film.titleKo.toLowerCase() : '';
    const director = typeof film?.director === 'string' ? film.director.toLowerCase() : '';
    return (
      titleEn.includes(normalizedQuery) ||
      titleKo.includes(normalizedQuery) ||
      director.includes(normalizedQuery)
    );
  });
}
