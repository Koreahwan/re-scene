import React, { useEffect, useState } from 'react';
import { AppModal } from './AppModal';
import { MovieCard } from './MovieCard';
import { filmsApi } from '../services/apiClient';
import { getVisualFixtureFilms } from '../testing/useVisualFixture';

export interface FilmsMoreModalProps {
  isOpen: boolean;
  onClose: () => void;
  navigate: (path: string) => void;
}

export const FilmsMoreModal: React.FC<FilmsMoreModalProps> = ({ isOpen, onClose, navigate }) => {
  console.log('FilmsMoreModal render, isOpen:', isOpen, 'fixture mode:', import.meta.env.VITE_VISUAL_FIXTURE_MODE);
  const [films, setFilms] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    async function loadFilms() {
      const fixtureFilms = getVisualFixtureFilms();
      if (fixtureFilms) {
        setFilms(fixtureFilms);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const res = await filmsApi.getFilms();
        if (isMounted) {
          const list = (res as any)?.data || (res as any) || [];
          setFilms(Array.isArray(list) ? list : []);
        }
      } catch (e) {
        if (isMounted) setFilms([]);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadFilms();
    return () => { isMounted = false; };
  }, [isOpen]);

  if (import.meta.env.VITE_VISUAL_FIXTURE_MODE === 'true') {
    if (!isOpen) return null;
    return (
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, background: '#FFFFFF', padding: '20px 0', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
        <div style={{ maxWidth: '1680px', margin: '0 auto', width: '100%', padding: '0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '16px' }}>
            <h1 style={{ fontSize: '28px', fontWeight: 700, color: '#2D2D34', margin: 0, lineHeight: 1 }}>
              영화
            </h1>
            <p style={{ fontSize: '15px', color: '#888888', margin: 0 }}>
              반전 이후 서사의 숨은 복선과 단서를 발견해보세요.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              width: '40px', height: '40px',
              borderRadius: '20px',
              border: '1px solid #EAEAEA',
              background: '#FFFFFF',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              color: '#111'
            }}
          >
            ×
          </button>
        </div>
        
        {loading ? (
          <div style={{ textAlign: 'center', padding: '100px', color: '#888' }}>로딩 중...</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '26px' }}>
            {films.map((film, idx) => (
              <MovieCard
                key={film.id || film.work_id || idx}
                id={film.id || film.work_id}
                title={film.title}
                year={film.year || film.release_year}
                rating={film.rating}
                genres={film.genres}
                reframeCount={film.reframeCount || film.total_reveals}
                size="xl"
                variant="grid"
                onClick={() => navigate(`/films/${film.id || film.work_id}`)}
              />
            ))}
          </div>
        )}
        </div>
      </div>
    );
  }

  return (
    <AppModal
      isOpen={isOpen}
      onClose={onClose}
      showCloseButton={import.meta.env.VITE_VISUAL_FIXTURE_MODE !== 'true'}
      backdropStyle={{ background: '#FFFFFF', zIndex: 9999 }}
      backdropClassName="films-more-backdrop"
      dialogStyle={{
        maxWidth: '100%',
        width: '100vw',
        height: '100vh',
        margin: 0,
        borderRadius: 0,
        boxShadow: 'none',
        background: '#FFFFFF',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        padding: 0
      }}
    >
      <div style={{ padding: import.meta.env.VITE_VISUAL_FIXTURE_MODE === 'true' ? '38px 40px' : '80px 40px', maxWidth: '1680px', margin: '0 auto', width: '100%', flex: 1 }}>
        {import.meta.env.VITE_VISUAL_FIXTURE_MODE !== 'true' && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: '40px' }}>
            <button
              onClick={onClose}
              style={{
                width: '40px', height: '40px',
                borderRadius: '20px',
                border: '1px solid #EAEAEA',
                background: '#FFFFFF',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '20px',
                color: '#111'
              }}
            >
              ×
            </button>
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: 'center', padding: '100px', color: '#888' }}>로딩 중...</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '26px' }}>
            {films.map((film, idx) => (
              <MovieCard
                key={film.id || film.work_id || idx}
                id={film.id || film.work_id}
                title={film.title}
                year={film.year || film.release_year}
                rating={film.rating}
                genres={film.genres}
                reframeCount={film.reframeCount || film.total_reveals}
                size="xl"
                variant="grid"
                onClick={() => navigate(`/films/${film.id || film.work_id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </AppModal>
  );
};
