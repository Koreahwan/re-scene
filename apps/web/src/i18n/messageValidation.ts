/**
 * Reframe V7 Dictionary Key Parity Validator
 */

import { enUS } from './messages/en-US';
import { koKR } from './messages/ko-KR';

export interface ValidationReport {
  isValid: boolean;
  totalKeys: number;
  missingInKo: string[];
  missingInEn: string[];
}

export function validateMessageDictionaries(): ValidationReport {
  const enKeys = new Set(Object.keys(enUS));
  const koKeys = new Set(Object.keys(koKR));

  const missingInKo: string[] = [];
  const missingInEn: string[] = [];

  for (const k of enKeys) {
    if (!koKeys.has(k)) missingInKo.push(k);
  }

  for (const k of koKeys) {
    if (!enKeys.has(k)) missingInEn.push(k);
  }

  return {
    isValid: missingInKo.length === 0 && missingInEn.length === 0,
    totalKeys: enKeys.size,
    missingInKo,
    missingInEn
  };
}

