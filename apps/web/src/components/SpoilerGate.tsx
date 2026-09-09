import React from 'react';
import { AppButton } from './AppButton';
import { SpoilerVisibility } from '../types/api';
import { LockIcon, ShieldCheckIcon } from './icons/AppIcons';
import { useLocale } from '../i18n/LocaleProvider';

export interface SpoilerGateProps {
  children?: React.ReactNode;
  visibility?: SpoilerVisibility;
  variant?: 'dialog' | 'inline';
  state?: 'locked' | 'revealed';
  safeTitle?: string;
  safePreview?: string;
  revealTitle?: string;
  spoilerScope?: string;
  onUnlock?: () => void;
  isLoading?: boolean;
}

export const SpoilerGate: React.FC<SpoilerGateProps> = ({
  children,
  visibility = 'LOCKED',
  safeTitle,
  safePreview,
  revealTitle,
  spoilerScope = 'the-bat-whispers-1930',
  onUnlock,
  isLoading = false
}) => {
  const { t } = useLocale();


  // STRICT SERVER-AUTHORITATIVE SPOILER GATE
  // No client-local bypass state allowed.
  const isVisible = visibility === 'VISIBLE';

  if (isVisible && children) {
    return <>{children}</>;
  }

  if (isVisible && !children) {
    return null;
  }

  const defaultRevealTitle = t('reveal.title');
  const title = safeTitle || revealTitle || defaultRevealTitle;
  const preview = safePreview || t('spoiler.lockedDesc');

  return (
    <div
      data-testid="spoiler-gate"
      style={{
        background: 'linear-gradient(135deg, #141926F2, #0A0D14FA)',
        border: '1px solid #F59E0B66',

        borderRadius: 'var(--radius-xl, 16px)',
        padding: '32px 28px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '16px',
        boxShadow: '0 8px 32px #00000099, 0 0 20px #F59E0B1A',
        maxWidth: '640px',
        margin: '0 auto',
        width: '100%'
      }}
    >
      <div
        style={{
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          background: '#F59E0B26',
          border: '1px solid #F59E0B80',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--accent-amber, #F59E0B)'
        }}
      >
        <LockIcon size={28} />
      </div>

      <div>
        <h3 style={{ fontSize: '20px', fontWeight: 800, color: '#FFFFFF', marginBottom: '8px' }}>
          {t('spoiler.badge')}
        </h3>
        <p style={{ fontSize: '15px', color: '#F1F5F9', fontWeight: 600, marginBottom: '6px' }}>
          [{title}]
        </p>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary, #CBD5E1)', lineHeight: 1.6, maxWidth: '480px', margin: 0 }}>
          {preview}
        </p>
      </div>

      <div
        style={{
          fontSize: '12px',
          color: 'var(--text-tertiary, #94A3B8)',
          background: '#0000004C',
          padding: '6px 14px',
          borderRadius: 'var(--radius-full, 9999px)',
          border: '1px solid var(--border-subtle, #FFFFFF14)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}
      >
        <ShieldCheckIcon size={14} color="var(--accent-green, #10B981)" />
        <span>
          {t('spoiler.scope')}: <code>{spoilerScope}</code>
        </span>
      </div>


      {onUnlock && (
        <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
          <AppButton
            variant="primary"
            size="md"
            onClick={onUnlock}
            isLoading={isLoading}
          >
            {t('spoiler.unlockBtn')}
          </AppButton>
        </div>
      )}
    </div>
  );
};

