/**
 * Reframe V7 Bilingual i18n Types
 * Strictly enforces en-US default (US Hackathon) and ko-KR secondary locale.
 */

export type SupportedLocale = 'en-US' | 'ko-KR';

export type LanguagePreference = 'SYSTEM' | SupportedLocale;

export interface LocaleContextType {
  locale: SupportedLocale;
  languagePreference: LanguagePreference;
  setLocale: (locale: SupportedLocale) => void;
  setLanguagePreference: (pref: LanguagePreference) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  formatDate: (date: Date | string | number, options?: Intl.DateTimeFormatOptions) => string;
  formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string;
  formatPercent: (value: number, options?: Intl.NumberFormatOptions) => string;
  formatRelativeTime: (value: number, unit: Intl.RelativeTimeFormatUnit) => string;
  formatDuration: (ms: number) => string;
}

export type TranslationDictionary = Record<string, string>;

