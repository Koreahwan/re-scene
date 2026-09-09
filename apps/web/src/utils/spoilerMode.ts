/**
 * Spoiler Mode Conversion Utilities
 * Handles bidirectional mapping between UI values and Backend API/storage values.
 */

export const normalizeMode = (mode?: string): string => {
  if (!mode) return 'STRICT_CUTOFF';
  if (mode === 'STRICT' || mode === 'STRICT_CUTOFF') return 'STRICT_CUTOFF';
  if (mode === 'ASK' || mode === 'WARN_AND_BLUR') return 'WARN_AND_BLUR';
  if (mode === 'ALL' || mode === 'OPEN_REVIEWS') return 'OPEN_REVIEWS';
  return mode;
};

export const toApiMode = (mode: string): string => {
  if (mode === 'STRICT_CUTOFF') return 'STRICT';
  if (mode === 'WARN_AND_BLUR') return 'ASK';
  if (mode === 'OPEN_REVIEWS') return 'ALL';
  return mode;
};
