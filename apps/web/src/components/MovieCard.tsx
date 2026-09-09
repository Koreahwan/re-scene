import React, { useState } from 'react';
import defaultPoster from '../assets/images/card_poster_default.png';
import batWhispersPoster from '../assets/images/poster_the_bat_whispers.jpg';
import heartSvg from '../assets/figma/heart.svg';

export const StarIcon: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = '#F2994A' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color} stroke={color} strokeWidth="1">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

export const BookmarkIcon: React.FC<{ size?: number; active?: boolean }> = ({ size = 16, active = false }) => (
  <img
    src={heartSvg}
    alt=""
    style={{
      width: `${size}px`,
      height: `${size}px`,
      filter: active ? 'invert(31%) sepia(93%) saturate(6000%) hue-rotate(345deg)' : 'none',
      opacity: active ? 1 : 0.6
    }}
  />
);

export const ReframeIcon: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = '#4C22F4' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
  </svg>
);

export interface MovieCardProps {
  id?: string;
  title: string;
  originalTitle?: string;
  year?: number | string;
  rating?: number | string;
  genres?: string[];
  reframeCount?: number;
  rank?: number;
  posterUrl?: string;
  size?: 'xl' | 'lg' | 'md' | 'sm';
  variant?: 'hero' | 'grid' | 'compact';
  state?: 'default' | 'hover';
  onClick?: () => void;
  onBookmark?: (e: React.MouseEvent) => void;
  isBookmarked?: boolean;
}

export const MovieCard: React.FC<MovieCardProps> = ({
  id,
  title,
  year = 1930,
  rating = 8.8,
  reframeCount,
  rank,
  posterUrl,
  size = 'md',
  variant,
  onClick,
  onBookmark,
  isBookmarked = false
}) => {
  const [bookmarked, setBookmarked] = useState(isBookmarked);

  const sizeMap = {
    xl: { width: '100%', maxWidth: '400px', imgHeight: '499px', titleSize: '16px' },
    lg: { width: '100%', maxWidth: '380px', imgHeight: '520px', titleSize: '18px' },
    md: { width: '100%', maxWidth: '280px', imgHeight: '380px', titleSize: '16px' },
    sm: { width: '100%', maxWidth: '200px', imgHeight: '270px', titleSize: '14px' }
  };

  const currentSize = sizeMap[size];
  const isFixtureMode = typeof import.meta !== 'undefined' && import.meta.env?.VITE_VISUAL_FIXTURE_MODE === 'true';
  const posterSrc = posterUrl || (isFixtureMode ? defaultPoster : (id === 'the-bat-whispers-1930' ? batWhispersPoster : defaultPoster));

  const handleBookmarkToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setBookmarked(!bookmarked);
    onBookmark?.(e);
  };

  return (
    <div
      onClick={onClick}
      style={{
        width: currentSize.width,
        maxWidth: currentSize.maxWidth,
        display: 'flex',
        flexDirection: 'column',
        gap: variant === 'grid' ? '27px' : '10px',
        cursor: 'pointer',
        position: 'relative',
        background: '#FFFFFF',
        borderRadius: '12px',
        transition: 'all 0.2s ease',
      }}
    >
      {/* Poster Image Container */}
      <div className="movie-card-poster" style={{
        width: '100%',
        height: currentSize.imgHeight,
        borderRadius: '12px',
        overflow: 'hidden',
        position: 'relative',
        background: '#F5F5F5',
        border: '1px solid #EEEEEE',
      }}>
        <img
          src={posterSrc}
          alt={title}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block',
          }}
        />

        {/* Rank Badge (Top Left) */}
        {rank !== undefined && (
          <div style={{
            position: 'absolute',
            top: '10px',
            left: '10px',
            width: '32px',
            height: '32px',
            borderRadius: '6px',
            background: '#2D2D34',
            color: '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: '16px',
          }}>
            {rank}
          </div>
        )}

        {/* Bookmark Button (Top Right) */}
        {variant !== 'grid' && (
          <button
          onClick={handleBookmarkToggle}
          aria-label={bookmarked ? 'Remove from favorites' : 'Add to favorites'}
          style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            background: '#FFFFFFE0',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 2px 6px #00000020'
          }}
        >
          <BookmarkIcon size={16} active={bookmarked} />
        </button>
        )}
      </div>

      {/* Metadata & Title */}
      <div className="movie-card-info" style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '0 2px' }}>
        <h3 style={{
            fontSize: currentSize.titleSize,
            fontWeight: 700,
            color: '#2D2D34',
            margin: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}>
            {title}
          </h3>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#888888' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
              <StarIcon size={12} />
              <span>{typeof rating === 'number' ? rating.toFixed(1) : rating}</span>
            </div>
            <span>•</span>
            <span>{year}</span>
            {reframeCount !== undefined && (
              <>
                <span>•</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#4C22F4', fontWeight: 600 }}>
                  <ReframeIcon size={12} />
                  <span>{reframeCount}</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
  );
};
