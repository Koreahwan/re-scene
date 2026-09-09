import React from 'react';
import { useLocale } from '../i18n/LocaleProvider';
import filmCoreLogoDark from '../assets/figma/film-core-logo-dark.svg';

interface FooterProps {
  navigate?: (path: string) => void;
}

export const Footer: React.FC<FooterProps> = () => {
  let isKo = false;
  try {
    const { locale } = useLocale();
    isKo = locale === 'ko-KR';
  } catch {
    // fallback if outside LocaleProvider
  }

  const policyItems = [
    { label: 'Terms and Policies', path: '/terms' },
    { label: 'Privacy Policy', path: '/privacy' },
    { label: 'Cookie Notice', path: '/service-terms' },
  ];

  const isDetail = typeof window !== 'undefined' && window.location.pathname.startsWith('/films/') && !window.location.pathname.startsWith('/films?');
  const footerHeight = isDetail ? '240px' : '220px';

  return (
    <footer
      data-testid="global-footer"
      data-layer="Footer"
      className="film-core-footer"
      style={{
        width: '100%',
        height: footerHeight,
        boxSizing: 'border-box',
        padding: '50px clamp(16px, 6.25vw, 120px)',
        background: '#4A4A53',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'flex-start',
      }}
    >
      <div
        className="film-core-footer-inner"
        style={{
          width: '100%',
          maxWidth: '1680px',
          height: '120px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        {/* Left */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-start',
            alignItems: 'flex-start',
            gap: '8px',
          }}
        >
          <div
            className="film-core-footer-logo-container"
            style={{
              width: '118px',
              height: '40px',
              boxSizing: 'border-box',
              paddingTop: '1px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <img
              src={filmCoreLogoDark}
              alt="RE:SCENE Logo"
              width="110.001"
              height="14.868"
              className="film-core-footer-logo-img"
              style={{
                width: '110.001px',
                height: '14.868px',
                display: 'block',
              }}
            />
          </div>
          <div
            className="film-core-footer-copy"
            style={{
              color: '#A8A7A4',
              fontSize: '16px',
              fontFamily: 'Pretendard, -apple-system, sans-serif',
              fontWeight: 500,
              lineHeight: '24px',
            }}
          >
            Copyright © RE:SCENE. All rights reserved.<br />
            REFRAMEtheSCENE@gmail.com
          </div>
        </div>

        {/* Right policy row */}
        <div
          className="film-core-footer-links"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '15px',
          }}
        >
          {policyItems.map((item, idx) => (
            <React.Fragment key={item.path}>
              {idx > 0 && (
                <div
                  className="film-core-footer-divider"
                  style={{ width: '1px', height: '16px', background: '#E3E1DF' }}
                />
              )}
              <span
                className="film-core-footer-link-text"
                style={{
                  color: '#A8A7A4',
                  fontSize: '14px',
                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                  fontWeight: 500,
                  lineHeight: '21px',
                  textAlign: 'right',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
                aria-label={item.label}
              >
                {item.label}
              </span>
            </React.Fragment>
          ))}
        </div>
      </div>
    </footer>
  );
};

