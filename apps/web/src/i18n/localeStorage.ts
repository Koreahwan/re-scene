/**
 * Reframe Phase 1 Locale Persistence & Resolution
 * In Phase 1, the English-Only User Surface principle strictly enforces 'en-US'
 * across all user-facing interfaces, regardless of URL query params, legacy saved
 * preferences, or browser language headers.
 */

import { SupportedLocale, LanguagePreference } from './localeTypes';

export const LOCALE_STORAGE_KEY = 'rescene.languagePreference';
export const DEFAULT_LOCALE: SupportedLocale = 'en-US';

export function getUrlLocaleOverride(): SupportedLocale | null {
  // Phase 1: URL parameter overrides cannot force non-English languages
  return null;
}

export function getSavedLanguagePreference(): LanguagePreference | null {
  return 'en-US';
}

export function saveLanguagePreference(_pref: LanguagePreference): void {
  // Phase 1: Always store 'en-US'
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en-US');
  } catch (err) {
    console.warn('Unable to save language preference to localStorage:', err);
  }
}

export function getBrowserLocale(): SupportedLocale {
  return DEFAULT_LOCALE;
}

export function resolveActiveLocale(): SupportedLocale {
  // Strict English-Only Rule for Phase 1
  return DEFAULT_LOCALE;
}
