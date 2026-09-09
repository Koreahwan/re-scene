import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { SupportedLocale, LanguagePreference, LocaleContextType } from './localeTypes';
import {
  resolveActiveLocale,
  getSavedLanguagePreference,
  saveLanguagePreference,
  DEFAULT_LOCALE
} from './localeStorage';
import { formatDate, formatNumber, formatPercent, formatRelativeTime, formatDuration } from './formatters';
import { enUS } from './messages/en-US';
import { koKR } from './messages/ko-KR';
import { apiClient } from '../services/apiClient';

const dictionaries: Record<SupportedLocale, Record<string, string>> = {
  'en-US': enUS,
  'ko-KR': koKR
};

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

export const LocaleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [preference, setPreference] = useState<LanguagePreference>(() => getSavedLanguagePreference() || 'en-US');
  const [activeLocale, setActiveLocale] = useState<SupportedLocale>(() => resolveActiveLocale());

  // Update HTML tag attributes and sync with API client on locale change
  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.lang = activeLocale;
      document.documentElement.dir = 'ltr';
    }
    // Update API client header
    apiClient.setLocale(activeLocale);
  }, [activeLocale]);

  // Handle URL override changes (e.g., ?lang=ko-KR) or manual preferences: Phase 1 strictly en-US
  const handleSetLocale = useCallback((_newLocale: SupportedLocale) => {
    setActiveLocale(DEFAULT_LOCALE);
    setPreference(DEFAULT_LOCALE);
    saveLanguagePreference(DEFAULT_LOCALE);
  }, []);

  const handleSetPreference = useCallback((_newPref: LanguagePreference) => {
    setPreference(DEFAULT_LOCALE);
    saveLanguagePreference(DEFAULT_LOCALE);
    setActiveLocale(DEFAULT_LOCALE);
  }, []);

  // Translation lookup with strict en-US enforcement for Phase 1
  const t = useCallback((key: string, params?: Record<string, string | number>): string => {
    const dict = dictionaries[DEFAULT_LOCALE];
    let message = dict[key] || key;

    if (params) {
      Object.entries(params).forEach(([paramKey, paramVal]) => {
        message = message.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), String(paramVal));
      });
    }

    return message;
  }, [activeLocale]);

  const value = useMemo<LocaleContextType>(() => ({
    locale: activeLocale,
    languagePreference: preference,
    setLocale: handleSetLocale,
    setLanguagePreference: handleSetPreference,
    t,
    formatDate: (d, opt) => formatDate(d, opt, activeLocale),
    formatNumber: (n, opt) => formatNumber(n, opt, activeLocale),
    formatPercent: (p, opt) => formatPercent(p, opt, activeLocale),
    formatRelativeTime: (v, u) => formatRelativeTime(v, u, activeLocale),
    formatDuration: (ms) => formatDuration(ms, activeLocale)
  }), [activeLocale, preference, handleSetLocale, handleSetPreference, t]);

  return (
    <LocaleContext.Provider value={value}>
      {children}
    </LocaleContext.Provider>
  );
};

export const useLocale = (): LocaleContextType => {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error('useLocale must be used within a LocaleProvider');
  }
  return context;
};

