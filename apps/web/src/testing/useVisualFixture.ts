/**
 * Hook to retrieve visual regression test fixtures.
 * Only returns fixture data when VITE_VISUAL_FIXTURE_MODE is explicitly 'true'.
 * In production builds / normal operation, returns null.
 */
import {
  FIGMA_FIXTURE_FILMS,
  FIGMA_FIXTURE_MAGAZINE,
  FIGMA_FIXTURE_COMMUNITY,
  FIGMA_FIXTURE_REVEALS,
  FIGMA_FIXTURE_MOMENTS,
  FIGMA_FIXTURE_SEARCH_RESULTS,
  FIGMA_SEARCH_TOTAL_COUNT,
  FIGMA_FIXTURE_FEATURED_FILMS,
  FIGMA_FIXTURE_MAIN_REFRAMED,
  FIGMA_FIXTURE_MAIN_REVIEWS,
  FIGMA_FIXTURE_MAIN_NOTICES,
  FIGMA_FIXTURE_MAIN_EDIT,
} from './fixtures/figmaTestFixtures';

export function isVisualFixtureMode(): boolean {
  if (typeof window !== 'undefined') {
    const search = window.location.search;
    if (search.includes('fixture=false') || search.includes('live=true')) {
      return false;
    }
  }
  return typeof import.meta !== 'undefined' && import.meta.env?.VITE_VISUAL_FIXTURE_MODE === 'true';
}

export function getVisualFixtureFeaturedFilms() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_FEATURED_FILMS : null;
}

export function getVisualFixtureMainReframed() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_MAIN_REFRAMED : null;
}

export function getVisualFixtureMainEdit() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_MAIN_EDIT : null;
}

export function getVisualFixtureMainReviews() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_MAIN_REVIEWS : null;
}

export function getVisualFixtureMainNotices() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_MAIN_NOTICES : null;
}

export function getVisualFixtureFilms() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_FILMS : null;
}

export function getVisualFixtureMagazine() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_MAGAZINE : null;
}

export function getVisualFixtureCommunity() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_COMMUNITY : null;
}

export function getVisualFixtureReveals() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_REVEALS : null;
}

export function getVisualFixtureMoments() {
  return isVisualFixtureMode() ? FIGMA_FIXTURE_MOMENTS : null;
}

export function getVisualFixtureSearch(query?: string) {
  if (!isVisualFixtureMode()) return null;
  const q = (query || '').trim().toLowerCase();
  if (q === 'whispers') {
    return {
      totalCount: FIGMA_SEARCH_TOTAL_COUNT,
      visibleResults: FIGMA_FIXTURE_SEARCH_RESULTS,
    };
  }
  return {
    totalCount: 0,
    visibleResults: [],
  };
}
