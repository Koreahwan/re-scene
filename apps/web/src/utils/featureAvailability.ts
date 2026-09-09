/**
 * Reframe Feature Availability Contract
 * Single source of truth for release gating between:
 * - Phase 1 Public Read-Only ('public_read_only')
 * - Local Preview / Test Profile ('local_preview')
 * - Visual Fixture Mode ('fixture')
 * - Phase 2 Production Auth ('full_production')
 */

export type ReleaseMode = 'public_read_only' | 'local_preview' | 'fixture' | 'full_production';

export interface FeatureAvailability {
  mode: ReleaseMode;
  isAuthAvailable: boolean;              // Whether auth/login/signup/me/csrf calls are active
  isCommunityAvailable: boolean;         // Whether community post listing/detail is active
  isWatchProgressSaveAvailable: boolean; // Whether users can save watch progress
  isTheoryRunAvailable: boolean;         // Whether users can run theory analysis
  isLocalOutboxAvailable: boolean;       // Whether local test email outbox is enabled
}

export function getReleaseMode(): ReleaseMode {
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_VISUAL_FIXTURE_MODE === 'true') {
    return 'fixture';
  }
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_LOCAL_PREVIEW === 'true') {
    return 'local_preview';
  }
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_ENABLE_PHASE2_AUTH === 'true') {
    return 'full_production';
  }
  return 'public_read_only';
}

export function getFeatureAvailability(): FeatureAvailability {
  const mode = getReleaseMode();

  switch (mode) {
    case 'fixture':
      return {
        mode,
        isAuthAvailable: false,
        isCommunityAvailable: false,
        isWatchProgressSaveAvailable: false,
        isTheoryRunAvailable: false,
        isLocalOutboxAvailable: false,
      };
    case 'local_preview':
      return {
        mode,
        isAuthAvailable: true,
        isCommunityAvailable: true,
        isWatchProgressSaveAvailable: true,
        isTheoryRunAvailable: typeof import.meta !== 'undefined' && import.meta.env?.VITE_ENABLE_THEORY_LAB === 'true',
        isLocalOutboxAvailable: true,
      };
    case 'full_production':
      return {
        mode,
        isAuthAvailable: true,
        isCommunityAvailable: true,
        isWatchProgressSaveAvailable: true,
        isTheoryRunAvailable: typeof import.meta !== 'undefined' && import.meta.env?.VITE_ENABLE_THEORY_LAB === 'true',
        isLocalOutboxAvailable: false,
      };
    case 'public_read_only':
    default:
      return {
        mode: 'public_read_only',
        isAuthAvailable: true,              // Phase 2: Auth is included per latest requirements
        isCommunityAvailable: true,         // Public reviews, comments, likes enabled
        isWatchProgressSaveAvailable: true,    // Browser session watch progress enabled
        isTheoryRunAvailable: false,        // Never enabled without explicit flag
        isLocalOutboxAvailable: false,
      };
  }
}

export function isAuthAvailable(): boolean {
  return getFeatureAvailability().isAuthAvailable;
}

export function isCommunityAvailable(): boolean {
  return getFeatureAvailability().isCommunityAvailable;
}

export function isWatchProgressSaveAvailable(): boolean {
  return getFeatureAvailability().isWatchProgressSaveAvailable;
}

export function isTheoryRunAvailable(): boolean {
  return getFeatureAvailability().isTheoryRunAvailable;
}

export function isLocalOutboxAvailable(): boolean {
  return getFeatureAvailability().isLocalOutboxAvailable;
}
