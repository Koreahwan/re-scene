/**
 * Reframe V7 Intl Formatters for Dates, Numbers, Percentages, Durations, and Relative Times.
 */

import { SupportedLocale } from './localeTypes';

export function formatDate(
  date: Date | string | number,
  options?: Intl.DateTimeFormatOptions,
  locale: SupportedLocale = 'en-US'
): string {
  try {
    const d = typeof date === 'object' ? date : new Date(date);
    if (isNaN(d.getTime())) return String(date);
    const defaultOptions: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      ...options
    };
    return new Intl.DateTimeFormat(locale, defaultOptions).format(d);
  } catch (err) {
    return String(date);
  }
}

export function formatNumber(
  value: number,
  options?: Intl.NumberFormatOptions,
  locale: SupportedLocale = 'en-US'
): string {
  try {
    return new Intl.NumberFormat(locale, options).format(value);
  } catch (err) {
    return String(value);
  }
}

export function formatPercent(
  value: number,
  options?: Intl.NumberFormatOptions,
  locale: SupportedLocale = 'en-US'
): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: 'percent',
      maximumFractionDigits: 1,
      ...options
    }).format(value);
  } catch (err) {
    return `${(value * 100).toFixed(1)}%`;
  }
}

export function formatRelativeTime(
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
  locale: SupportedLocale = 'en-US'
): string {
  try {
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    return rtf.format(value, unit);
  } catch (err) {
    return `${value} ${unit} ago`;
  }
}

export function formatDuration(ms: number, locale: SupportedLocale = 'en-US'): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (locale === 'ko-KR') {
    if (hours > 0) {
      return `${hours}시간 ${minutes}분 ${seconds}초`;
    }
    return `${minutes}분 ${seconds}초`;
  }

  // en-US
  const pad = (n: number) => String(n).padStart(2, '0');
  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${minutes}:${pad(seconds)}`;
}

