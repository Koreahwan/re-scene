import React, { useEffect, useState } from 'react';

// Shared visual source for Browse Films and the live weekend chart.
export function RankedFilmCard({ title, rank, posterPath, badge, metadata, onClick, testId, fallbackPoster }: {
  title: string; rank: number; posterPath?: string; badge: string; metadata: React.ReactNode;
  onClick: () => void; testId?: string; fallbackPoster?: string;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [posterPath]);
  return <div role="button" tabIndex={0} aria-label={`View film details: ${title}`}
    onClick={onClick} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onClick(); } }}
    data-layer="MovieCard" data-testid={testId} className="ranked-film-card"
    style={{ width: 'var(--ranked-poster-width, 350px)', flexShrink: 0, flexDirection: 'column', alignItems: 'center', gap: 24, display: 'inline-flex', cursor: 'pointer' }}>
    <div data-testid="ranked-film-poster" style={{ width: '100%', aspectRatio: '350 / 437', position: 'relative', background: '#F2F2F5', overflow: 'hidden', borderRadius: 12 }}>
      {posterPath && !failed ? <img style={{ width: '100%', height: '100%', objectFit: 'cover' }} src={posterPath} alt={`${title} poster`}
        referrerPolicy="no-referrer" onError={event => {
          if (fallbackPoster && event.currentTarget.getAttribute('src') !== fallbackPoster) event.currentTarget.src = fallbackPoster;
          else setFailed(true);
        }} /> : <p style={{ padding: 24, marginTop: 160, textAlign: 'center', color: '#6B6B75' }}>Poster unavailable</p>}
      <div style={{ width: '76.857%', height: '83.066%', left: '11.314%', top: '9.153%', position: 'absolute', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
        <div style={{ alignSelf: 'stretch', display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ padding: '6px 10px', background: 'rgba(0,0,0,0.5)', borderRadius: 6, color: 'white', fontSize: 14, fontFamily: 'Pretendard', fontWeight: 500 }}>{badge}</div>
        </div>
        <div style={{ color: 'white', fontSize: 'var(--ranked-number-size, 70px)', fontFamily: 'Pretendard', fontWeight: 800, textShadow: '0px 0px 40px rgba(0,0,0,0.6)' }}>{rank}</div>
      </div>
    </div>
    <div style={{ alignSelf: 'stretch', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div data-testid="ranked-film-title" style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: 600 }}>{title}</div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 24, color: 'var(--Gray-800, #2D2D34)', fontSize: 14, fontFamily: 'Pretendard' }}>{metadata}</div>
    </div>
  </div>;
}
