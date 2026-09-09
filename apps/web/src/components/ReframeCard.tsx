import React from 'react';
import { useLocale } from '../i18n/LocaleProvider';
import { AppButton } from './AppButton';
import { ClockIcon, SparklesIcon, PlayIcon, DocumentTextIcon } from './icons/AppIcons';
import { mapTrustNamespace } from '../utils/trustMapper';

export interface ReframedMoment {
  id: string;
  sceneId?: string;
  startMs?: number;
  endMs?: number;
  timestampFormatted?: string;
  preRevealMeaning: string;
  postRevealMeaning: string;
  evidenceType?: string;
  confidenceScore?: number;
  verificationStatus?: string;
  trustNamespace?: string;
  humanReviewStatus?: string;
  keyFrameUrl?: string;
}

export interface ReframeCardProps {
  moment: ReframedMoment;
  onRewatchScene?: (startMs?: number) => void;
  onViewProof?: (momentId: string) => void;
}

export const ReframeCard: React.FC<ReframeCardProps> = ({
  moment,
  onRewatchScene,
  onViewProof
}) => {
  const { t } = useLocale();
  const badge = mapTrustNamespace(
    moment.trustNamespace,
    moment.verificationStatus,
    moment.humanReviewStatus
  );

  return (
    <div style={{
      background: 'var(--bg-surface, #12141C)',
      border: '1px solid var(--border-default, #FFFFFF26)',
      borderRadius: 'var(--radius-xl, 16px)',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      boxShadow: 'var(--shadow-sm, 0 1px 2px 0 #00000080)',
      transition: 'all 0.25s ease',
    }}>
      {/* Top Header: Timestamp & Evidence Status */}
      <div style={{
        padding: '16px 20px',
        background: 'var(--bg-surface-raised, #1A1D2A)',
        borderBottom: '1px solid var(--border-subtle, #FFFFFF14)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {moment.timestampFormatted && (
            <span style={{
              fontSize: '14px',
              fontWeight: 800,
              color: '#FFFFFF',
              fontFamily: 'var(--font-code, monospace)',
              background: '#00000066',
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm, 4px)',
              border: '1px solid #FFFFFF1A',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <ClockIcon size={14} color="#C084FC" />
              <span>{moment.timestampFormatted}</span>
            </span>
          )}
          {moment.sceneId && (
            <span style={{ fontSize: '13px', color: 'var(--text-tertiary, #94A3B8)', fontWeight: 600 }}>
              {t('reframe.sceneId')}: {moment.sceneId}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            title={badge.description}
            style={{
              fontSize: '11px',
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: 'var(--radius-full, 9999px)',
              background: badge.bgColor,
              color: badge.textColor,
              border: `1px solid ${badge.borderColor}`
            }}
          >
            {badge.badgeText}
          </span>
          {moment.confidenceScore !== undefined && (
            <span style={{
              fontSize: '12px',
              fontWeight: 700,
              color: 'var(--accent-cyan, #06B6D4)',
              background: '#06B6D41F',
              padding: '4px 8px',
              borderRadius: 'var(--radius-sm, 4px)'
            }}>
              {t('reframe.confidence')} {(moment.confidenceScore * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {/* Before vs After Reframe Comparison Grid */}
      <div style={{
        padding: '24px 20px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '20px'
      }}>
        {/* Pre-Reveal Meaning */}
        <div style={{
          background: '#00000040',
          border: '1px solid #FFFFFF14',
          borderRadius: 'var(--radius-lg, 12px)',
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted, #64748B)', textTransform: 'uppercase' }}>
              {t('reframe.preReveal')}
            </span>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary, #CBD5E1)', lineHeight: 1.6, margin: 0 }}>
            {moment.preRevealMeaning}
          </p>
        </div>

        {/* Post-Reveal Reframe Meaning */}
        <div style={{
          background: '#A855F714',
          border: '1px solid #A855F759',
          borderRadius: 'var(--radius-lg, 12px)',
          padding: '16px 18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          boxShadow: '0 0 20px #A855F71A'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <SparklesIcon size={14} color="#C084FC" />
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#C084FC', textTransform: 'uppercase' }}>
              {t('reframe.postReveal')}
            </span>
          </div>
          <p style={{ fontSize: '14px', color: '#FFFFFF', fontWeight: 600, lineHeight: 1.6, margin: 0 }}>
            {moment.postRevealMeaning}
          </p>
        </div>
      </div>

      {/* Action Bar */}
      <div style={{
        padding: '12px 20px 16px',
        borderTop: '1px solid var(--border-subtle, #FFFFFF14)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ fontSize: '13px', color: 'var(--text-tertiary, #94A3B8)' }}>
          {moment.evidenceType ? (
            <span>{t('reframe.evidenceType')}: <strong style={{ color: '#FFFFFF' }}>{moment.evidenceType}</strong></span>
          ) : (
            <span>{badge.label}</span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {onViewProof && (
            <AppButton
              variant="outline"
              size="sm"
              icon={<DocumentTextIcon size={14} />}
              onClick={() => onViewProof(moment.id)}
            >
              {t('reframe.viewProof')}
            </AppButton>
          )}
          {onRewatchScene && (
            <AppButton
              variant="primary"
              size="sm"
              icon={<PlayIcon size={14} />}
              onClick={() => onRewatchScene(moment.startMs)}
            >
              {t('reframe.jumpToScene')}
            </AppButton>
          )}
        </div>
      </div>
    </div>
  );
};

