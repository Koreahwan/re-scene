import React, { useState, useEffect, useRef } from 'react';
import { filmsApi } from '../services/apiClient';
import { SortOptions, movieSortOptions } from '../components/SortOptions';
import { compareRanking } from '../utils/contentRanking';
import { DemoFilmNotice } from '../components/DemoFilmNotice';
import { Pagination } from '../components/Pagination';
import {
  FilmCatalogItemViewModel,
  mapFilmCatalogResponse,
} from './filmCatalogViewModel';
import { isVisualFixtureMode, getVisualFixtureFilms } from '../testing/useVisualFixture';

interface FilmMorePageProps {
  navigate?: (path: string) => void;
}

export const FilmMorePage: React.FC<FilmMorePageProps> = ({ navigate }) => {
  const [films, setFilms] = useState<FilmCatalogItemViewModel[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(!isVisualFixtureMode());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [categoryFallback, setCategoryFallback] = useState(0);
  const [sort, setSort] = useState('newest');
  const [page, setPage] = useState(1);
  useEffect(() => { setPage(1); }, [sort, categoryFallback, window.location.search]);
  const [retryTrigger, setRetryTrigger] = useState<number>(0);
  const reqIdRef = useRef<number>(0);

  const categories = [
    'All',
    'Thriller',
    'Mystery',
    'Horror',
    'Classic',
    'Sci-Fi',
    'Action',
    'Drama',
    'Crime',
    'Romance',
  ];
  const requestedGenre = new URLSearchParams(window.location.search).get('genre');
  const selectedCategory = requestedGenre ? Math.max(0, categories.indexOf(requestedGenre)) : navigate ? 0 : categoryFallback;
  const setSelectedCategory = (index: number) => {
    setCategoryFallback(index);
    if (navigate) {
      const params = new URLSearchParams(window.location.search);
      params.set('modal', 'all');
      params.set('genre', categories[index]);
      navigate(`/films?${params}`);
    }
  };

  useEffect(() => {
    const fixture = getVisualFixtureFilms();
    if (isVisualFixtureMode()) {
      if (fixture) {
        const parseResult = mapFilmCatalogResponse({
          data: fixture.map((f: any) => ({ ...f, movie_id: f.movie_id || f.id })),
          total: fixture.length,
          page: 1,
          limit: 30,
        });
        if (parseResult.success) {
          setFilms(parseResult.films);
        }
      }
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    let isMounted = true;
    const currentReqId = ++reqIdRef.current;

    async function loadCatalog() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const res = await filmsApi.getAllFilms();
        if (!isMounted || currentReqId !== reqIdRef.current) return;

        const parseResult = mapFilmCatalogResponse(res);
        if (parseResult.success && parseResult.films.length > 0) {
          setFilms(parseResult.films);
          setErrorMessage(null);
        } else if (fixture) {
          const fallback = mapFilmCatalogResponse({
            data: fixture.map((f: any) => ({ ...f, movie_id: f.movie_id || f.id })),
            total: fixture.length,
            page: 1,
            limit: 30,
          });
          if (fallback.success) {
            setFilms(fallback.films);
          }
        }
      } catch (err: any) {
        if (!isMounted || currentReqId !== reqIdRef.current) return;
        if (fixture) {
          const fallback = mapFilmCatalogResponse({
            data: fixture.map((f: any) => ({ ...f, movie_id: f.movie_id || f.id })),
            total: fixture.length,
            page: 1,
            limit: 30,
          });
          if (fallback.success) {
            setFilms(fallback.films);
            setErrorMessage(null);
          }
        } else {
          setErrorMessage(err?.message || 'Failed to load film catalog.');
          setFilms([]);
        }
      } finally {
        if (isMounted && currentReqId === reqIdRef.current) {
          setIsLoading(false);
        }
      }
    }

    loadCatalog();
    return () => {
      isMounted = false;
    };
  }, [retryTrigger]);

  const handleRetry = () => {
    setRetryTrigger((prev) => prev + 1);
  };

  const selectedCategoryName = categories[selectedCategory];
  const categoryFilms = selectedCategory === 0
    ? films
    : films.filter((f) => {
        if (!f.genres || f.genres.length === 0) return false;
        return f.genres.some((g) => {
          const ko = (g.name_ko || '').toLowerCase();
          const en = (g.name_en || '').toLowerCase();
          const target = selectedCategoryName.toLowerCase();
          if (target === 'thriller') return ko.includes('스릴러') || en.includes('thriller');
          if (target === 'mystery') return ko.includes('미스터리') || en.includes('mystery');
          if (target === 'horror') return ko.includes('공포') || en.includes('horror');
          if (target === 'classic') return ko.includes('고전') || en.includes('classic');
          if (target === 'sci-fi') return ko.includes('sf') || en.includes('science fiction') || en.includes('sci-fi');
          if (target === 'action') return ko.includes('액션') || en.includes('action');
          if (target === 'drama') return ko.includes('드라마') || en.includes('drama');
          if (target === 'crime') return ko.includes('범죄') || en.includes('crime');
          if (target === 'romance') return ko.includes('로맨스') || en.includes('romance');
          return ko.includes(target) || en.includes(target);
        });
      });

  const filteredFilms = [...categoryFilms].sort((a, b) => {
    return compareRanking(a, b, sort) || a.movieId.localeCompare(b.movieId, 'en');
  });

  return (
    <div
      data-layer="영화 - 더보기 선택시"
      className="film-more-page"
      style={{
        width: '100%',
        maxWidth: 1920,
        margin: '0 auto',
        position: 'relative',
        background: 'var(--Gray-0, white)',
        flexDirection: 'column',
        display: 'flex',
      }}
    >
      <div
        data-layer="Frame 2147227211"
        style={{
          alignSelf: 'stretch',
          flexDirection: 'column',
          justifyContent: 'flex-start',
          alignItems: 'flex-start',
          display: 'flex',
        }}
      >
        <div
          data-layer="Frame 2147227204"
          style={{
            alignSelf: 'stretch',
            flexDirection: 'column',
            justifyContent: 'flex-start',
            alignItems: 'flex-start',
            display: 'flex',
          }}
        >
          <div
            data-layer="Frame 2147227301"
            style={{
              alignSelf: 'stretch',
              flexDirection: 'column',
              justifyContent: 'flex-start',
              alignItems: 'flex-start',
              display: 'flex',
            }}
          >
            {/* Core Demo Notice Banner */}
            <div
              data-testid="core-demo-notice-banner"
              style={{
                alignSelf: 'stretch',
                paddingTop: 24,
                paddingLeft: 120,
                paddingRight: 120,
              }}
            >
              <div
                style={{
                  padding: '12px 20px',
                  background: 'var(--Purple-50, #F1F0FF)',
                  border: '1px solid var(--Purple-200, #B7B3FF)',
                  borderRadius: 12,
                  color: 'var(--Purple-700, #3412B3)',
                  fontSize: 14,
                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span>ℹ️</span>
                <DemoFilmNotice films={films} navigate={navigate} />
              </div>
            </div>

            {/* Category Chips (1:1 Figma Frame 2147227197) */}
            <div
              data-layer="Frame 2147227197"
              style={{
                alignSelf: 'stretch',
                paddingTop: 30,
                paddingLeft: 120,
                paddingRight: 120,
                flexDirection: 'column',
                justifyContent: 'flex-start',
                alignItems: 'flex-start',
                gap: 10,
                display: 'flex',
              }}
            >
              <div
                data-layer="Frame 2147227193"
                style={{
                  width: '100%',
                  maxWidth: 1680,
                  flexDirection: 'column',
                  justifyContent: 'flex-start',
                  alignItems: 'flex-start',
                  gap: 24,
                  display: 'flex',
                }}
              >
                <div
                  data-layer="Frame 2147227287"
                  style={{
                    alignSelf: 'stretch',
                    justifyContent: 'flex-start',
                    alignItems: 'flex-start',
                    gap: 16,
                    display: 'flex',
                    flexWrap: 'wrap',
                  }}
                >
                  {categories.map((cat, idx) => (
                    <button
                      key={idx}
                      type="button"
                      data-testid={`category-chip-${cat}`}
                      onClick={() => setSelectedCategory(idx)}
                      data-layer="CategoryChip"
                      data-state={selectedCategory === idx ? 'Pressed' : 'Default'}
                      style={{
                        padding: '10px 20px',
                        background:
                          selectedCategory === idx
                            ? 'var(--Gray-700, #4A4A53)'
                            : 'var(--Gray-100, #F2F2F5)',
                        borderRadius: 20,
                        border: 'none',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <span
                        style={{
                          color:
                            selectedCategory === idx
                              ? 'var(--Gray-0, white)'
                              : 'var(--Gray-700, #4A4A53)',
                          fontSize: 18,
                          fontFamily: 'Pretendard',
                          fontWeight: 500,
                          lineHeight: '22px',
                        }}
                      >
                        {cat}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="catalog-sort-bar">
              <span>Total {filteredFilms.length} films</span>
              <SortOptions label="Sort movies" value={sort} onChange={setSort} options={movieSortOptions} />
            </div>
            {/* Movies List Area */}
            {isLoading ? (
              <div
                data-testid="catalog-loading"
                style={{
                  width: '100%',
                  minHeight: 400,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--Gray-500, #898992)',
                  fontSize: 18,
                  fontFamily: 'Pretendard',
                }}
              >
                Loading films...
              </div>
            ) : errorMessage ? (
              <div
                data-testid="catalog-error"
                style={{
                  width: '100%',
                  minHeight: 400,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 16,
                  color: '#D32F2F',
                  fontSize: 18,
                  fontFamily: 'Pretendard',
                }}
              >
                <div>{errorMessage}</div>
                <button
                  type="button"
                  data-testid="catalog-retry-button"
                  onClick={handleRetry}
                  style={{
                    padding: '10px 24px',
                    backgroundColor: '#2D2D34',
                    color: '#FFFFFF',
                    borderRadius: 8,
                    border: 'none',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: 14,
                  }}
                >
                  Retry
                </button>
              </div>
            ) : filteredFilms.length === 0 ? (
              <div
                data-testid="catalog-empty"
                style={{
                  width: '100%',
                  minHeight: 400,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 16,
                  color: 'var(--Gray-500, #898992)',
                  fontSize: 18,
                  fontFamily: 'Pretendard',
                }}
              >
                <div>No films found for genre '{selectedCategoryName}'.</div>
                <button
                  type="button"
                  onClick={() => setSelectedCategory(0)}
                  style={{
                    padding: '8px 20px',
                    borderRadius: 20,
                    border: '1px solid #4A4A53',
                    background: 'none',
                    cursor: 'pointer',
                    fontSize: 14,
                    color: '#4A4A53',
                  }}
                >
                  View All Films
                </button>
              </div>
            ) : (
              /* Movie Cards Grid (1:1 Figma Frame 2147227198) */
              <div
                data-layer="Frame 2147227198"
                className="film-more-grid"
                style={{
                  alignSelf: 'stretch',
                  paddingTop: 24,
                  paddingBottom: 70,
                  paddingLeft: 121,
                  paddingRight: 121,
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 400px))',
                  columnGap: 26,
                  rowGap: 36,
                  justifyContent: 'center',
                }}
              >
                {filteredFilms.slice((page - 1) * 12, page * 12).map((movie, idx) => (
                  <div
                    key={movie.movieId}
                    data-testid={`film-more-card-${movie.movieId}`}
                    data-layer="MovieCard"
                    data-size="Lg"
                    tabIndex={0}
                    role="button"
                    aria-label={`${movie.title} (${movie.year || 'Year unavailable'})`}
                    onClick={() => navigate && navigate(movie.destination)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate && navigate(movie.destination);
                      }
                    }}
                    style={{
                      width: '100%',
                      maxWidth: 400,
                      flexDirection: 'column',
                      justifyContent: 'flex-start',
                      alignItems: 'center',
                      gap: 16,
                      display: 'inline-flex',
                      cursor: 'pointer',
                      outline: 'none',
                    }}
                  >
                    <div
                      data-layer="Frame 2147227300"
                      style={{
                        width: '100%',
                        height: 499,
                        position: 'relative',
                        background: '#E6E6EA',
                        overflow: 'hidden',
                        borderRadius: 12,
                        aspectRatio: '400 / 499',
                      }}
                    >
                      {movie.posterPath ? (
                        <img
                          data-layer="Thumbnail"
                          style={{
                            width: '100%',
                            height: 499,
                            objectFit: 'cover',
                            display: 'block',
                          }}
                          src={movie.posterPath}
                          alt={`${movie.title} poster`}
                          loading={idx < 4 ? 'eager' : 'lazy'}
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <div
                          data-testid="no-poster-placeholder"
                          role="img"
                          aria-label={`Poster unavailable for ${movie.title}`}
                          style={{
                            width: '100%',
                            height: '100%',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: 8,
                            color: '#898992',
                            fontSize: 16,
                            fontFamily: 'Pretendard',
                          }}
                        >
                          <span style={{ fontSize: 32 }}>🎬</span>
                          <span>Poster unavailable</span>
                        </div>
                      )}
                    </div>
                    <div
                      data-layer="Frame 2147227224"
                      style={{
                        alignSelf: 'stretch',
                        flexDirection: 'column',
                        justifyContent: 'flex-start',
                        alignItems: 'center',
                        gap: 6,
                        display: 'flex',
                      }}
                    >
                      <div
                        data-layer="영화 제목"
                        data-testid="film-more-card-title"
                        style={{
                          alignSelf: 'stretch',
                          textAlign: 'center',
                          color: 'var(--Gray-800, #2D2D34)',
                          fontSize: 18,
                          fontFamily: 'Pretendard',
                          fontWeight: 600,
                          lineHeight: '24px',
                          wordBreak: 'keep-all',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {movie.title}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Pagination page={page} total={filteredFilms.length} onChange={setPage} />
          </div>
        </div>
      </div>
    </div>
  );
};
