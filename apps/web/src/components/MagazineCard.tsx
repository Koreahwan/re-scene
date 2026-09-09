import React from 'react';
import defaultHero1 from '../assets/images/magazine_hero_1.png';
import defaultHero2 from '../assets/images/magazine_hero_2.jpg';

export const ShieldCheckIcon: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = '#27AE60' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <polyline points="9 12 11 14 15 10" />
  </svg>
);

export const ShieldAlertIcon: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = '#EB5757' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

export const ClockIcon: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = '#888888' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

export interface MagazineCardProps {
  id: string;
  title: string;
  subtitle?: string;
  category?: string;
  author?: string;
  readTimeMin?: number;
  publishedAt?: string;
  coverImageUrl?: string;
  isSpoilerSafe?: boolean;
  onClick?: () => void;
}

export const MagazineCard: React.FC<MagazineCardProps> = ({
  id,
  title,
  subtitle,
  category = '영화 분석',
  author = '에디터',
  readTimeMin = 5,
  publishedAt = '2026.08.20',
  coverImageUrl,
  isSpoilerSafe = true,
  onClick
}) => {
  const coverSrc = coverImageUrl || (id.charCodeAt(0) % 2 === 0 ? defaultHero1 : defaultHero2);

  return (
    <div
      data-testid="magazine-card"
      onClick={onClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: '#FFFFFF',
        border: '1px solid #EEEEEE',
        borderRadius: '12px',
        overflow: 'hidden',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: '0 2px 8px #00000008'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 8px 20px #00000012';
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '0 2px 8px #00000008';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      {/* Cover Image */}
      <div className="magazine-card-image" style={{
        width: '100%',
        height: '200px',
        position: 'relative',
        overflow: 'hidden',
        background: '#F5F5F5'
      }}>
        <img
          src={coverSrc}
          alt={title}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block'
          }}
        />

        {/* Category Badge */}
        <div style={{
          position: 'absolute',
          top: '12px',
          left: '12px',
          padding: '4px 10px',
          borderRadius: '9999px',
          background: '#FFFFFFE0',
          color: '#4C22F4',
          fontSize: '12px',
          fontWeight: 700
        }}>
          {category}
        </div>

        {/* Spoiler Shield Badge */}
        <div style={{
          position: 'absolute',
          top: '12px',
          right: '12px',
          padding: '4px 8px',
          borderRadius: '9999px',
          background: '#FFFFFFE0',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          fontSize: '11px',
          fontWeight: 600,
          color: isSpoilerSafe ? '#27AE60' : '#EB5757'
        }}>
          {isSpoilerSafe ? <ShieldCheckIcon size={12} /> : <ShieldAlertIcon size={12} />}
          <span>{isSpoilerSafe ? '스포일러 안심' : '스포일러 포함'}</span>
        </div>
      </div>

      {/* Content Area */}
      <div className="magazine-card-info" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
        <h3 style={{
          fontSize: '18px',
          fontWeight: 700,
          color: '#2D2D34',
          lineHeight: 1.4,
          margin: 0,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden'
        }}>
          {title}
        </h3>

        {subtitle && (
          <p style={{
            fontSize: '14px',
            color: '#555555',
            lineHeight: 1.5,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden'
          }}>
            {subtitle}
          </p>
        )}

        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: 'auto',
          paddingTop: '12px',
          borderTop: '1px solid #EEEEEE',
          fontSize: '13px',
          color: '#888888'
        }}>
          <span>{author}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
              <ClockIcon size={12} />
              <span>{readTimeMin}분</span>
            </div>
            <span>•</span>
            <span>{publishedAt}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
