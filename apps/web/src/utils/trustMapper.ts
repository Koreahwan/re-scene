import { TrustNamespace, HumanReviewStatus } from '../types/api';

export interface TrustBadgeConfig {
  label: string;
  badgeText: string;
  badgeLevel: 'D4' | 'D3' | 'COMMUNITY' | 'UNVERIFIED' | 'ABSTAINED';
  bgColor: string;
  textColor: string;
  borderColor: string;
  description: string;
}

export function mapTrustNamespace(
  trustNamespace?: TrustNamespace | string,
  verificationStatus?: string,
  _humanReviewStatus?: HumanReviewStatus | string,
  _locale: 'en-US' | 'ko-KR' = 'en-US'
): TrustBadgeConfig {
  // Phase 1 strictly enforces English surface unconditionally
  // Strict rule: Only CANONICAL_VERIFIED + VERIFIED_CANON gets D4 / VERIFIED CANON badge
  if (
    trustNamespace === 'CANONICAL_VERIFIED' &&
    verificationStatus === 'VERIFIED_CANON'
  ) {
    return {
      label: 'Verified Canon Evidence (D4)',
      badgeText: '✓ VERIFIED CANON',
      badgeLevel: 'D4',
      bgColor: '#10B98126',
      textColor: '#34D399',
      borderColor: '#34D39966',
      description: 'Mathematically verified timestamped evidence from ClickHouse narrative memory.'
    };
  }

  // Engine inference
  if (trustNamespace === 'ENGINE_INFERENCE') {
    return {
      label: 'Narrative Engine Inference (D3)',
      badgeText: '⚡ ENGINE INFERENCE',
      badgeLevel: 'D3',
      bgColor: '#A855F726',
      textColor: '#C084FC',
      borderColor: '#A855F766',
      description: 'Strong causal inference linking multiple observed structural clues.'
    };
  }

  // Observed evidence / canonical facts
  if (trustNamespace === 'OBSERVED_EVIDENCE' || trustNamespace === 'CANONICAL_FACT') {
    return {
      label: 'Observed Visual Evidence (D1/D2)',
      badgeText: '👁️ OBSERVED FACT',
      badgeLevel: 'D4',
      bgColor: '#38BDF826',
      textColor: '#38BDF8',
      borderColor: '#38BDF866',
      description: 'Observable factual clues directly visible at scene frame timestamps.'
    };
  }

  // Community interpretation
  if (trustNamespace === 'COMMUNITY_INTERPRETATION') {
    return {
      label: 'Community Theory / Hypothesis',
      badgeText: '👥 COMMUNITY CLAIM',
      badgeLevel: 'COMMUNITY',
      bgColor: '#F59E0B26',
      textColor: '#FBBF24',
      borderColor: '#F59E0B66',
      description: 'Community-proposed interpretation submitted for forensic verification.'
    };
  }

  // Abstained
  if (verificationStatus === 'ABSTAINED' || trustNamespace === 'ABSTAINED') {
    return {
      label: 'Forensic Abstained (Insufficient Evidence)',
      badgeText: '⚠️ ABSTAINED',
      badgeLevel: 'ABSTAINED',
      bgColor: '#64748B33',
      textColor: '#94A3B8',
      borderColor: '#94A3B84C',
      description: 'Rejected due to insufficient evidence, conflict, or lack of causal link.'
    };
  }

  // Default unvalidated state
  return {
    label: 'Pending Verification',
    badgeText: '⏳ NOT VALIDATED',
    badgeLevel: 'UNVERIFIED',
    bgColor: '#FFFFFF14',
    textColor: '#CBD5E1',
    borderColor: '#FFFFFF26',
    description: 'Item is pending forensic pipeline processing and evidence verification.'
  };
}
