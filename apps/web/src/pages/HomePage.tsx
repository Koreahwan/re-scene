import React, { useEffect, useState, useRef } from 'react';
import { filmsApi, magazineApi, communityApi } from '../services/apiClient';
import {
  FilmCatalogItemViewModel,
  mapFilmCatalogResponse,
  filterFilmsByQuery,
} from './filmCatalogViewModel';
import {
  getVisualFixtureFeaturedFilms,
  getVisualFixtureFilms,
  getVisualFixtureMainEdit,
  getVisualFixtureMainNotices,
  getVisualFixtureMainReviews,
  getVisualFixtureSearch,
  isVisualFixtureMode,
} from '../testing/useVisualFixture';
import { DeferredImage } from '../components/DeferredImage';
import { isCommunityAvailable } from '../utils/featureAvailability';
import { Pagination } from '../components/Pagination';

interface SearchResultFilm {
  id?: string;
  movie_id?: string;
  movieId?: string;
  title: string;
  year?: string | number;
  poster_path?: string;
  posterPath?: string | null;
  destination?: string;
}

const SEARCH_POSTER_TRANSFORMS: Record<
  string,
  {
    position: 'absolute';
    width: string;
    height: string;
    left: string;
    top: string;
    maxWidth: string;
    objectFit: 'cover';
  }
> = {
  '/assets/figma-current/search/the-bat-whispers-1930.png': {
    position: 'absolute',
    width: '448px',
    height: '672px',
    left: '-24px',
    top: '-86px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/whispers-next-door-2026.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-66px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/whispers-2019.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-68px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/whispers-1941.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-51px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/russian-whispers-2019.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-51px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/whispers-1990.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-51px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/angel-whispers-2015.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-50px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
  '/assets/figma-current/search/whispers-in-the-dark-1992.png': {
    position: 'absolute',
    width: '400px',
    height: '600px',
    left: '0px',
    top: '-50px',
    maxWidth: 'none',
    objectFit: 'cover',
  },
};

function getSearchPosterTransform(posterPath?: string | null) {
  if (!posterPath) return null;
  const cleanPath = posterPath.split('?')[0];
  for (const [key, transform] of Object.entries(SEARCH_POSTER_TRANSFORMS)) {
    if (cleanPath === key || cleanPath.endsWith(key) || ('/' + cleanPath) === key) {
      return transform;
    }
  }
  return null;
}

interface HomePageProps {
  searchQuery?: string;
  navigate: (path: string) => void;
}

export const HomePage: React.FC<HomePageProps> = ({ searchQuery = '', navigate }) => {
  const [searchPage, setSearchPage] = useState(1);
  useEffect(() => { setSearchPage(1); }, [searchQuery]);
  const section = new URLSearchParams(window.location.search).get('section');
  useEffect(() => {
    if (section === 'faq') document.getElementById('faq')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [section]);
  const [catalogFilms, setCatalogFilms] = useState<FilmCatalogItemViewModel[]>([]);
  const [liveEditItems, setLiveEditItems] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(!isVisualFixtureMode());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Dedicated server-backed search state with race-condition prevention
  const [searchResults, setSearchResults] = useState<FilmCatalogItemViewModel[]>([]);
  const [searchTotal, setSearchTotal] = useState<number>(0);
  const [searchLoading, setSearchLoading] = useState<boolean>(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [magazineError, setMagazineError] = useState<string | null>(null);

  const [liveReviews, setLiveReviews] = useState<Array<{ id: string; filmTitle: string; rating: number; body: string; destination: string }>>([]);
  const [reviewsLoading, setReviewsLoading] = useState<boolean>(false);
  const [reviewsError, setReviewsError] = useState<string | null>(null);

  const [retryTrigger, setRetryTrigger] = useState<number>(0);
  const catalogReqIdRef = useRef<number>(0);
  const searchReqIdRef = useRef<number>(0);

  const isFixture = isVisualFixtureMode();
  const trimmedQuery = searchQuery ? searchQuery.trim() : '';
  const isSearchMode = trimmedQuery.length > 0;

  // 1. Initial Catalog & Bottom Content Loading (when not in search-only fixture mode)
  useEffect(() => {
    if (isVisualFixtureMode()) {
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    let isMounted = true;
    const currentReqId = ++catalogReqIdRef.current;

    async function loadCatalog() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const filmsRes = await filmsApi.getFilms({ offset: 0, limit: 50 });
        if (!isMounted || currentReqId !== catalogReqIdRef.current) {
          return;
        }

        const parseResult = mapFilmCatalogResponse(filmsRes);
        if (!parseResult.success) {
          setErrorMessage(parseResult.error);
          setCatalogFilms([]);
        } else {
          setCatalogFilms(parseResult.films);
          setErrorMessage(null);
        }
      } catch (err: any) {
        if (!isMounted || currentReqId !== catalogReqIdRef.current) {
          return;
        }
        setErrorMessage(err?.message || 'Failed to fetch catalog from server');
        setCatalogFilms([]);
      } finally {
        if (isMounted && currentReqId === catalogReqIdRef.current) {
          setIsLoading(false);
        }
      }
    }

    // Live articles for RE:SCENE Edit (Non-blocking parallel fetch)
    async function loadMagazine() {
      try {
        const articlesRes = await magazineApi.listArticles();
        if (isMounted && currentReqId === catalogReqIdRef.current && articlesRes?.articles) {
          // Editorial self-published articles only for Edit section, max 4 cards.
          const editorialArticles = articlesRes.articles.filter((art: any) => !art.is_synthetic && !art.isSynthetic);
          const mapped = editorialArticles.slice(0, 4).map((art: any) => ({
            id: art.article_id || art.id || `art-${art.title}`,
            editor: art.author_alias || art.authorAlias || 'Reframe Editorial',
            title: art.title,
            imagePath: art.hero_image_url || '/assets/figma-current/main/edit/mystery-viewings.jpeg',
            destination: `/magazine/${encodeURIComponent(art.article_id || art.id)}`,
            isSynthetic: false,
          }));
          setLiveEditItems(mapped);
          setMagazineError(null);
        }
      } catch (err: any) {
        if (isMounted && currentReqId === catalogReqIdRef.current) {
          setLiveEditItems([]);
          setMagazineError('Could not load editorial articles. Please try again.');
        }
      }
    }


    async function loadReviews() {
      setReviewsLoading(true);
      setReviewsError(null);
      try {
        const postsRes = await communityApi.listPosts('the-bat-whispers-1930', undefined, 'popular');
        if (isMounted && currentReqId === catalogReqIdRef.current) {
          const posts = (postsRes as any)?.data || (Array.isArray(postsRes) ? postsRes : []);
          const mapped = posts.slice(0, 4).map((post: any) => {
            const isLocked = post.is_spoiler_locked === true;
            const safeBody = isLocked
              ? 'This review contains spoiler-protected discussion.'
              : (post.change_summary || post.body_markdown || post.body || 'Audience review for The Bat Whispers');
            return {
              id: post.post_id || post.id,
              filmTitle: 'The Bat Whispers',
              rating: typeof post.rating === 'number' ? post.rating : null,
              body: safeBody,
              destination: '/films/the-bat-whispers-1930',
            };
          });
          setLiveReviews(mapped);
          setReviewsError(null);
        }
      } catch (err: any) {
        if (isMounted && currentReqId === catalogReqIdRef.current) {
          setLiveReviews([]);
          setReviewsError(err?.message || 'Failed to load audience reviews.');
        }
      } finally {
        if (isMounted && currentReqId === catalogReqIdRef.current) {
          setReviewsLoading(false);
        }
      }
    }

    loadCatalog();
    loadMagazine();

    loadReviews();

    return () => {
      isMounted = false;
    };
  }, [retryTrigger]);

  // 2. Real Server-Backed Search Execution
  useEffect(() => {
    if (isVisualFixtureMode() || !isSearchMode) {
      setSearchResults([]);
      setSearchTotal(0);
      setSearchLoading(false);
      setSearchError(null);
      return;
    }

    let isMounted = true;
    const currentSearchReqId = ++searchReqIdRef.current;
    setSearchLoading(true);
    setSearchError(null);

    async function executeSearch() {
      try {
        // Query PostgreSQL backend via /api/v1/films?q={query}&offset=0&limit=50
        const res = await filmsApi.getFilms({ q: trimmedQuery, offset: (searchPage - 1) * 12, limit: 12 });
        if (!isMounted || currentSearchReqId !== searchReqIdRef.current) return;

        const parseResult = mapFilmCatalogResponse(res);
        if (!parseResult.success) {
          setSearchError(parseResult.error);
          setSearchResults([]);
          setSearchTotal(0);
        } else {
          setSearchResults(parseResult.films);
          setSearchTotal(res.meta?.total ?? parseResult.films.length);
          setSearchError(null);
        }
      } catch (err: any) {
        if (!isMounted || currentSearchReqId !== searchReqIdRef.current) return;
        setSearchError('Could not load search results. Please try again.');
        setSearchResults([]);
        setSearchTotal(0);
      } finally {
        if (isMounted && currentSearchReqId === searchReqIdRef.current) {
          setSearchLoading(false);
        }
      }
    }

    // Run search request
    executeSearch();

    return () => {
      isMounted = false;
    };
  }, [trimmedQuery, retryTrigger, searchPage]);

  const handleRetry = () => {
    setRetryTrigger((prev) => prev + 1);
  };

  const fixtureSearch = isFixture && isSearchMode ? getVisualFixtureSearch(trimmedQuery) : null;
  const fixtureFeatured = isFixture ? getVisualFixtureFeaturedFilms() : null;
  const fixtureEdit = isFixture ? getVisualFixtureMainEdit() : null;
  const fixtureReviews = isFixture ? getVisualFixtureMainReviews() : null;
  const fixtureNotices = isFixture ? getVisualFixtureMainNotices() : null;

  // True server-backed counts and items in live mode; preserved 1:1 fixtures in test mode
  const totalCount = isFixture
    ? (fixtureSearch ? fixtureSearch.totalCount : 0)
    : searchTotal;
  const displayResults: SearchResultFilm[] = isFixture
    ? (fixtureSearch ? fixtureSearch.visibleResults : [])
    : searchResults.map((film) => ({
        id: film.movieId,
        movieId: film.movieId,
        title: film.title,
        year: film.year,
        posterPath: film.posterPath,
        destination: film.destination,
      }));

  const featuredFilms = isFixture
    ? (fixtureFeatured || [
        { rank: 1, id: 'the-bat-whispers-1930', title: 'The Bat Whispers', posterPath: '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I8-28118-73-6268.png', destination: '/films/the-bat-whispers-1930' },
        { rank: 2, id: 'the-bat-whispers-1930-2', title: 'The Bat Whispers', posterPath: '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I73-6857-73-6268.png', destination: '/films/the-bat-whispers-1930' },
        { rank: 3, id: 'the-bat-whispers-1930-3', title: 'The Bat Whispers', posterPath: '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I73-6868-73-6268.png', destination: '/films/the-bat-whispers-1930' },
        { rank: 4, id: 'the-bat-whispers-1930-4', title: 'The Bat Whispers', posterPath: '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I73-6901-73-6268.png', destination: '/films/the-bat-whispers-1930' },
        { rank: 5, id: 'the-bat-whispers-1930-5', title: 'The Bat Whispers', posterPath: '/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I73-6879-73-6268.png', destination: '/films/the-bat-whispers-1930' },
      ])
    : catalogFilms.map((film, index) => ({
        rank: index + 1,
        id: film.movieId,
        movieId: film.movieId,
        title: film.title,
        posterPath: film.posterPath,
        destination: film.destination,
      }));

  const editItems = isFixture
    ? (fixtureEdit || [
        {
          id: 'edit-1',
          editor: 'MJay, Culture Editor',
          title: 'How Many Viewings Does It Take to Fully Appreciate a Mystery Movie?',
          imagePath: '/assets/figma-current/main/edit/mystery-viewings.jpeg',
          destination: '/magazine',
        },
        {
          id: 'edit-2',
          editor: 'KRhwan, Film Editor',
          title: 'How much harder is it for viewers to notice foreshadowing in horror movies than in other genres?',
          imagePath: '/assets/figma-current/main/edit/horror-foreshadowing.jpeg',
          destination: '/magazine',
        },
        {
          id: 'edit-3',
          editor: 'Wooj, Reviews Editor',
          title: 'Do Spoilers Really Ruin the Movie Experience?',
          imagePath: '/assets/figma-current/main/edit/spoilers-movie-experience.jpeg',
          destination: '/magazine',
        },
        {
          id: 'edit-4',
          editor: 'Hyejin, Visual Editor',
          title: 'The Unseen Hand: Directorial Shadows in Classic Thrillers',
          imagePath: '/assets/figma-current/main/edit/mystery-viewings.jpeg',
          destination: '/magazine',
        },
        {
          id: 'edit-5',
          editor: 'Hyejin, Visual Editor',
          title: 'Frame by Frame: Reconstructing the Final Clue',
          imagePath: '/assets/figma-current/main/edit/horror-foreshadowing.jpeg',
          destination: '/magazine',
        },
      ])
    : liveEditItems;

  const reviewItems = isFixture
    ? (fixtureReviews || [1, 2, 3, 4].map((i) => ({
        id: `review-${i}`,
        filmTitle: 'The Bat Whispers',
        rating: 4,
        body: 'A compelling mystery that challenges your assumptions from beginning to end.',
        destination: '/films/the-bat-whispers-1930',
      })))
    : liveReviews;

  const noticeItems: Array<{ id: string; label: string; destination?: string }> = isFixture
    ? (fixtureNotices || [
        { id: 'notice-1', label: 'How do I use RE:SCENE?' },
        { id: 'notice-2', label: 'I don’t want any plot points or foreshadowing spoiled.' },
        { id: 'notice-3', label: 'I forgot my ID.' },
      ])
    : [
        { id: 'notice-1', label: 'How do I use RE:SCENE?' },
        { id: 'notice-2', label: 'I don’t want any plot points or foreshadowing spoiled.' },
        { id: 'notice-3', label: 'I forgot my ID.' },
      ];

  // --------------------------------------------------------------------------
  // SEARCH RESULTS VIEW (Figma Frame 73:6268)
  // --------------------------------------------------------------------------
  if (isSearchMode) {
    if (!isFixture && searchLoading) {
      return (
        <div
          data-testid="search-results-loading"
          style={{
            width: '100%',
            height: '680px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#6B6B75',
            fontSize: '20px',
            fontFamily: 'Pretendard, -apple-system, sans-serif',
          }}
        >
          Searching film catalog...
        </div>
      );
    }

    if (!isFixture && searchError) {
      return (
        <div
          data-testid="search-results-error"
          style={{
            width: '100%',
            height: '680px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '16px',
            color: '#D32F2F',
            fontSize: '18px',
            fontFamily: 'Pretendard, -apple-system, sans-serif',
          }}
        >
          <div>{searchError}</div>
          <button
            type="button"
            data-testid="search-retry-button"
            onClick={handleRetry}
            style={{
              padding: '10px 24px',
              backgroundColor: '#2D2D34',
              color: '#FFFFFF',
              borderRadius: '8px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '14px',
            }}
          >
            Retry
          </button>
        </div>
      );
    }

    // Zero-state empty search view (1:1 Figma Frame 73:6268 with totalCount = 0)
    if (totalCount === 0 || displayResults.length === 0) {
      return (
        <div
          data-layer="메인화면 - 검색결과 없음"
          data-testid="search-empty"
          style={{
            width: '100%',
            background: '#FFFFFF',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Title strip: 90px height, 121px horizontal padding */}
          <div
            data-testid="search-title"
            className="search-title-strip"
            style={{
              width: '100%',
              height: '90px',
              boxSizing: 'border-box',
              padding: '28px 121px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <div
              style={{
                color: '#2D2D34',
                fontSize: '24px',
                fontFamily: 'Pretendard, -apple-system, sans-serif',
                fontWeight: 600,
                lineHeight: '33.6px',
                maxWidth: '100%',
                overflowWrap: 'break-word',
                wordBreak: 'break-word',
              }}
            >
              Search results for “{trimmedQuery}”
            </div>
          </div>

          {/* Empty content region: 680px height, centered horizontally & vertically */}
          <div
            data-layer="ContentPlaceholder"
            className="search-empty-container"
            style={{
              width: '100%',
              height: '680px',
              boxSizing: 'border-box',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
            }}
          >
            {/* 100x100 Alert-style SVG */}
            <div style={{ width: '100px', height: '100px', marginBottom: '32px' }}>
              <svg width="100" height="100" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M49.9997 91.6668C73.0115 91.6668 91.6663 73.012 91.6663 50.0002C91.6663 26.9883 73.0115 8.3335 49.9997 8.3335C26.9878 8.3335 8.33301 26.9883 8.33301 50.0002C8.33301 73.012 26.9878 91.6668 49.9997 91.6668Z" fill="#D4D4DA" />
                <path d="M49.9997 33.3335V50.0002M49.9997 66.6668H50.0413M91.6663 50.0002C91.6663 73.012 73.0115 91.6668 49.9997 91.6668C26.9878 91.6668 8.33301 73.012 8.33301 50.0002C8.33301 26.9883 26.9878 8.3335 49.9997 8.3335C73.0115 8.3335 91.6663 26.9883 91.6663 50.0002Z" stroke="#FFFFFF" strokeWidth="8.33333" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>

            {/* Text group */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
              <div
                style={{
                  textAlign: 'center',
                  color: '#2D2D34',
                  fontSize: '20px',
                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                  fontWeight: 400,
                  lineHeight: '28px',
                  maxWidth: '100%',
                  overflowWrap: 'break-word',
                  wordBreak: 'break-word',
                }}
              >
                No results found for “{trimmedQuery}.”
              </div>
              <div
                style={{
                  textAlign: 'center',
                  color: '#6B6B75',
                  fontSize: '18px',
                  fontFamily: 'Pretendard, -apple-system, sans-serif',
                  fontWeight: 500,
                  lineHeight: '27px',
                }}
              >
                Check your spelling or<br />try a different keyword.
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div
        data-layer="메인화면 - 검색결과"
        data-testid="search-results"
        style={{
          width: '100%',
          background: '#FFFFFF',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Title strip: 90px */}
        <div
          data-testid="search-title"
          className="search-title-strip"
          style={{
            width: '100%',
            height: '90px',
            boxSizing: 'border-box',
            padding: '28px 120px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              color: '#2D2D34',
              fontSize: '24px',
              fontFamily: 'Pretendard, -apple-system, sans-serif',
              fontWeight: 600,
              lineHeight: '33.6px',
              paddingTop: '1px',
              maxWidth: '100%',
              overflowWrap: 'break-word',
              wordBreak: 'break-word',
            }}
          >
            Search results for “{trimmedQuery}”
          </div>
        </div>

        {/* Sort/header bar: 62px */}
        <div
          data-testid="search-sortbar"
          className="search-sortbar"
          style={{
            width: '100%',
            height: '62px',
            boxSizing: 'border-box',
            padding: '20px 121px',
            borderBottom: '1px solid #F2F2F5',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              color: '#2D2D34',
              fontSize: '18px',
              fontFamily: 'Pretendard, -apple-system, sans-serif',
              fontWeight: 600,
            }}
          >
            Total {totalCount}
          </div>
        </div>

        {/* Grid: 1232px height, 4 cols x 2 rows */}
        <div
          data-testid="search-results-grid"
          className="search-results-grid"
          style={{
            width: '100%',
            minHeight: '600px',
            boxSizing: 'border-box',
            padding: '50px 121px 70px 121px',
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 400px)',
            columnGap: '26px',
            rowGap: '24px',
          }}
        >
          {(isFixture ? displayResults.slice((searchPage - 1) * 12, searchPage * 12) : displayResults).map((film: SearchResultFilm, idx: number) => {
            const filmId = film.movieId || film.movie_id || film.id || '';
            const destination = film.destination || `/films/${encodeURIComponent(filmId)}`;
            const poster = film.posterPath !== undefined ? film.posterPath : film.poster_path;
            const posterTransform = getSearchPosterTransform(poster);
            return (
              <button
                key={filmId || idx}
                type="button"
                data-testid="search-result-card"
                onClick={() => navigate(destination)}
                aria-label={film.title || 'Movie Poster'}
                style={{
                  width: '400px',
                  height: '544px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  cursor: 'pointer',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  margin: 0,
                  textAlign: 'inherit',
                  font: 'inherit',
                }}
              >
                <div
                  style={{
                    width: '400px',
                    height: '499px',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    background: '#F0F0F0',
                    position: 'relative',
                  }}
                >
                  {poster ? (
                    posterTransform ? (
                      <DeferredImage
                        src={poster}
                        alt={film.title || 'Movie Poster'}
                        data-has-transform="true"
                        style={{
                          position: posterTransform.position,
                          width: posterTransform.width,
                          height: posterTransform.height,
                          left: posterTransform.left,
                          top: posterTransform.top,
                          maxWidth: posterTransform.maxWidth,
                          objectFit: posterTransform.objectFit,
                          display: 'block',
                        }}
                      />
                    ) : (
                      <DeferredImage
                        src={poster}
                        alt={film.title || 'Movie Poster'}
                        style={{
                          width: '100%',
                          height: '100%',
                          objectFit: 'cover',
                          display: 'block',
                        }}
                      />
                    )
                  ) : (
                    <div
                      data-testid="no-poster-placeholder"
                      style={{
                        width: '100%',
                        height: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: '#E4E4E8',
                        color: '#898992',
                        fontSize: '16px',
                        fontWeight: 500,
                      }}
                    >
                      No Poster
                    </div>
                  )}
                </div>
                <div
                  data-testid="catalog-item-title"
                  style={{
                    marginTop: '24px',
                    height: '21px',
                    width: '100%',
                    textAlign: 'center',
                    color: '#2D2D34',
                    fontSize: '18px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    lineHeight: '21px',
                  }}
                >
                  {(() => {
                    const rawTitle = (film.title || '').trim();
                    return rawTitle || 'Untitled Film';
                  })()}
                </div>
              </button>
            );
          })}
        </div>
        <Pagination page={searchPage} total={totalCount} onChange={setSearchPage} />
      </div>
    );
  }

  // --------------------------------------------------------------------------
  // MAIN HOME VIEW (1:1 Figma Frame 5:3171)
  // --------------------------------------------------------------------------
  return (
    <div data-layer="메인화면" style={{ width: '100%', background: 'var(--Gray-0, white)', flexDirection: 'column', display: 'flex' }}>
      {/* Top Banner (1680x400) */}
      <div
        data-layer="Frame 2147227212"
        className="home-banner-wrapper"
        style={{
          width: '100%',
          height: '460px',
          boxSizing: 'border-box',
          padding: '30px 120px',
          background: '#FFFFFF',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
        }}
      >
        <div
          data-layer="배너"
          className="home-banner-container"
          data-node-id="666:4972"
          style={{
            width: '100%',
            maxWidth: 1680,
            height: 400,
            borderRadius: 12,
            overflow: 'hidden',
            position: 'relative',
            background: 'linear-gradient(90deg, #CCC8FF 0%, #F1F0FF 100%)',
            boxSizing: 'border-box',
          }}
        >
          {/* Left Text Block (Figma 666:4983) */}
          <div
            className="home-banner-content"
            data-node-id="666:4983"
            style={{
              position: 'absolute',
              left: 95,
              top: '50%',
              transform: 'translateY(-50%)',
              display: 'flex',
              flexDirection: 'column',
              gap: 24,
              maxWidth: 1000,
              zIndex: 2,
            }}
          >
            <div
              className="home-banner-title"
              data-node-id="666:4975"
              style={{
                fontFamily: "'Paperlogy', 'Paperlogy:7_Bold', 'Pretendard', sans-serif",
                fontWeight: 700,
                fontSize: 55,
                lineHeight: 'normal',
                color: '#08051F',
                margin: 0,
              }}
            >
              <div>Curious</div>
              <div>What’s Behind the Movie?</div>
            </div>
            <div
              className="home-banner-desc"
              data-node-id="666:4977"
              style={{
                fontFamily: "'Pretendard', -apple-system, sans-serif",
                fontWeight: 300,
                fontSize: 20,
                lineHeight: 'normal',
                color: '#08051F',
                margin: 0,
              }}
            >
              Pick a movie on RE: SCENE and discover the stories behind it.
            </div>
          </div>

          {/* Right Decorative Elements */}
          <div
            className="home-banner-decorations"
            aria-hidden="true"
            style={{
              position: 'absolute',
              inset: 0,
              pointerEvents: 'none',
              overflow: 'hidden',
            }}
          >
            {/* Ellipse glow ring (Figma 666:4987) */}
            <div
              style={{
                position: 'absolute',
                left: 1001,
                top: 75,
                width: 1080,
                height: 814.5,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <div style={{ transform: 'rotate(-18.92deg)' }}>
                <img
                  src="/assets/banner/ellipse-3414.svg"
                  alt=""
                  style={{ width: 959, height: 532, display: 'block' }}
                />
              </div>
            </div>

            {/* Projector Image (Figma 666:4981) */}
            <div
              style={{
                position: 'absolute',
                left: 1124.928,
                top: 14,
                width: 372,
                height: 372,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <div style={{ transform: 'rotate(-7.58deg) scaleX(-1)', width: 331.025, height: 331.025 }}>
                <img
                  src="/assets/banner/projector.png"
                  alt=""
                  className="home-banner-projector"
                  style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                />
              </div>
            </div>

            {/* Small dots and star */}
            <img
              src="/assets/banner/ellipse-3415.svg"
              alt=""
              style={{ position: 'absolute', left: 1157, top: 196, width: 7, height: 7 }}
            />
            <img
              src="/assets/banner/ellipse-3416.svg"
              alt=""
              style={{ position: 'absolute', left: 1490, top: 328, width: 7, height: 7 }}
            />
            <img
              src="/assets/banner/star-8.svg"
              alt=""
              style={{ position: 'absolute', left: 1121.4782, top: 160.9139, width: 26.0436, height: 24.9645 }}
            />
          </div>
        </div>
      </div>

      {/* Main Content Sections */}
      <div data-layer="Frame 2147227211" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
        <div data-layer="Frame 2147227204" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
          
          {/* Section 1: Featured Films */}
          <div
            data-layer="Frame 2147227194"
            className="home-featured-section"
            style={{
              width: '100%',
              height: '673px',
              boxSizing: 'border-box',
              padding: '50px 120px 0 120px',
              background: '#FFFFFF',
              position: 'relative',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
            }}
          >
            <div
              data-layer="Frame 2147227193"
              className="home-featured-inner"
              style={{
                width: '1680px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
              }}
            >
              <div
                style={{
                  width: '1680px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div
                  data-layer="Featured Films"
                  style={{
                    height: '39px',
                    color: '#2D2D34',
                    fontSize: '28px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    fontWeight: 600,
                    lineHeight: '39.2px',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  RE:SCENE’s Pick
                </div>
                <div
                  data-testid="core-demo-notice-text"
                  style={{
                    color: '#898992',
                    fontSize: '14px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                  }}
                >
                  Explore featured films and share your perspective.
                </div>
              </div>
              <div
                data-layer="Frame 2147227222"
                className="home-featured-row"
                style={{
                  width: '1680px',
                  height: '490px',
                  marginTop: '24px',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                }}
              >
                {/* 1608px clip area */}
                <div
                  data-testid="featured-strip-container"
                  className="home-featured-strip"
                  style={{
                    width: '1608px',
                    height: '490px',
                    overflow: 'hidden',
                    position: 'relative',
                    display: 'flex',
                    gap: '12px',
                    flexShrink: 0,
                  }}
                >
                  {!isFixture && isLoading ? (
                    <div
                      data-testid="catalog-loading"
                      style={{
                        width: '100%',
                        height: '437px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#6B6B75',
                        fontSize: '18px',
                        fontFamily: 'Pretendard, -apple-system, sans-serif',
                      }}
                    >
                      Loading film catalog...
                    </div>
                  ) : !isFixture && errorMessage ? (
                    <div
                      data-testid="catalog-error"
                      style={{
                        width: '100%',
                        height: '437px',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '16px',
                        color: '#D32F2F',
                        fontSize: '18px',
                        fontFamily: 'Pretendard, -apple-system, sans-serif',
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
                          borderRadius: '8px',
                          border: 'none',
                          cursor: 'pointer',
                          fontWeight: 600,
                          fontSize: '14px',
                        }}
                      >
                        Retry
                      </button>
                    </div>
                  ) : !isFixture && featuredFilms.length === 0 ? (
                    <div
                      data-testid="featured-empty"
                      style={{
                        width: '100%',
                        height: '437px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#898992',
                        fontSize: '18px',
                        fontFamily: 'Pretendard, -apple-system, sans-serif',
                      }}
                    >
                      No featured films are available yet.
                    </div>
                  ) : (
                    featuredFilms.map((film) => (
                      <button
                        key={film.id}
                        type="button"
                        onClick={() => navigate(film.destination)}
                        aria-label={`${film.rank} ${film.title}`}
                        data-layer="MovieCard"
                        data-testid="featured-film-card"
                        style={{
                          width: '350px',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          cursor: 'pointer',
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          margin: 0,
                          font: 'inherit',
                          flexShrink: 0,
                        }}
                      >
                        <div
                          data-layer="Frame 2147227300"
                          style={{
                            width: '350px',
                            height: '437px',
                            position: 'relative',
                            borderRadius: '12px',
                            overflow: 'hidden',
                            background: '#F0F0F0',
                          }}
                        >
                          {film.posterPath ? (
                            <DeferredImage
                              src={film.posterPath}
                              alt={film.title}
                              {...(film.rank === 1 ? { fetchPriority: 'high' } : {})}
                              style={{
                                width: '100%',
                                height: '100%',
                                objectFit: 'cover',
                                display: 'block',
                              }}
                            />
                          ) : (
                            <div
                              data-testid="no-poster-placeholder"
                              style={{
                                width: '100%',
                                height: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                background: '#E4E4E8',
                                color: '#898992',
                                fontSize: '18px',
                                fontWeight: 500,
                              }}
                            >
                              No Poster
                            </div>
                          )}
                          <div
                            data-layer="Rank"
                            style={{
                              position: 'absolute',
                              left: '40px',
                              bottom: '34px',
                              color: '#FFFFFF',
                              fontSize: '70px',
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 800,
                              lineHeight: 1,
                              textShadow: '0px 0px 39.6px rgba(0, 0, 0, 0.60)',
                              pointerEvents: 'none',
                            }}
                          >
                            {film.rank}
                          </div>
                        </div>
                        <div
                          data-testid="featured-film-title"
                          style={{
                            marginTop: '24px',
                            height: '21px',
                            width: '100%',
                            textAlign: 'center',
                            color: '#2D2D34',
                            fontSize: '18px',
                            fontFamily: 'Pretendard, -apple-system, sans-serif',
                            fontWeight: 600,
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            lineHeight: '21px',
                          }}
                        >
                          {film.title}
                        </div>
                      </button>
                    ))
                  )}
                </div>

                {/* Next button: 60x437, radius 16, gap 12 from clip */}
                <button
                  type="button"
                  aria-label="Next featured films"
                  onClick={() => navigate('/films')}
                  data-layer="NextButton"
                  className="home-featured-next-button"
                  style={{
                    width: '60px',
                    height: '437px',
                    background: '#F2F2F5',
                    borderRadius: '16px',
                    border: 'none',
                    padding: 0,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <svg width="60" height="437" viewBox="0 0 60 437" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect width="60" height="437" rx="16" fill="#F2F2F5" />
                    <path d="M26 226.5L34 218.5L26 210.5" stroke="#4A4A53" strokeWidth="2.66667" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
            </div>
          </div>



          {/* Section 3: RE:SCENE Edit */}
          <div
            data-layer="Frame 2147227195"
            className="home-edit-section"
            style={{
              width: '100%',
              height: '546px',
              boxSizing: 'border-box',
              paddingLeft: 120,
              paddingRight: 120,
              paddingTop: 50,
              paddingBottom: 50,
              background: '#FFFFFF',
              flexDirection: 'column',
              justifyContent: 'flex-start',
              alignItems: 'flex-start',
              gap: 10,
              display: 'flex',
              overflow: 'hidden',
            }}
          >
            <div
              data-layer="Frame 2147227183"
              className="home-edit-inner"
              style={{
                alignSelf: 'stretch',
                width: 1680,
                height: 446,
                flexDirection: 'column',
                justifyContent: 'flex-start',
                alignItems: 'flex-start',
                gap: 35,
                display: 'flex',
              }}
            >
              <div
                data-layer="Frame 2147227205"
                style={{
                  alignSelf: 'stretch',
                  width: 1680,
                  height: 39,
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  display: 'inline-flex',
                }}
              >
                <div
                  data-layer="The RE:SCENE Edit"
                  style={{
                    color: 'var(--Gray-800, #2D2D34)',
                    fontSize: 28,
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    fontWeight: 600,
                    lineHeight: '39.2px',
                  }}
                >
                  The RE:SCENE Edit
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/magazine')}
                  aria-label="View more magazine articles"
                  data-layer="Frame 2147227206"
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    margin: 0,
                    width: 57,
                    height: 20,
                    justifyContent: 'flex-end',
                    alignItems: 'center',
                    gap: 4,
                    display: 'inline-flex',
                    cursor: 'pointer',
                  }}
                >
                  <span
                    data-layer="More"
                    style={{
                      color: 'var(--Gray-500, #898992)',
                      fontSize: 14,
                      fontFamily: 'Pretendard, -apple-system, sans-serif',
                      fontWeight: 400,
                      lineHeight: '20px',
                    }}
                  >
                    More
                  </span>
                  <div data-layer="chevron-right" style={{ width: 20, height: 20, position: 'relative', overflow: 'hidden', flexShrink: 0 }}>
                    <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M7.5 15L12.5 10L7.5 5" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.66667" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                </button>
              </div>
              {editItems.length === 0 ? (
                <div
                  data-testid="empty-edit-state"
                  style={{
                    width: '100%',
                    padding: '40px 0',
                    color: '#898992',
                    fontSize: '16px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                  }}
                >
                  No editorial articles are available yet.
                </div>
              ) : (
                <div
                  data-layer="Frame 2147227180"
                  className="home-edit-row"
                  style={{
                    alignSelf: 'stretch',
                    width: 1680,
                    height: 372,
                    justifyContent: 'flex-start',
                    alignItems: 'flex-start',
                    gap: 20,
                    display: 'flex',
                  }}
                >
                  {editItems.slice(0, 4).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => navigate(item.destination)}
                      aria-label={`${item.editor}: ${item.title}`}
                      data-layer="Frame 2147227178"
                      style={{
                        width: 320,
                        height: 372,
                        flexShrink: 0,
                        flexDirection: 'column',
                        justifyContent: 'flex-start',
                        alignItems: 'flex-start',
                        gap: 20,
                        display: 'flex',
                        cursor: 'pointer',
                        border: 'none',
                        background: 'none',
                        padding: 0,
                        margin: 0,
                        textAlign: 'left',
                      }}
                    >
                      <div
                        data-layer="Frame 2147227179"
                        style={{
                          width: 320,
                          height: 232,
                          borderRadius: 12,
                          overflow: 'hidden',
                          position: 'relative',
                          backgroundColor: '#E5E5EA',
                          flexShrink: 0,
                        }}
                      >
                        <div
                          style={{
                            width: 320,
                            height: 400,
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            overflow: 'hidden',
                          }}
                        >
                          <DeferredImage
                            src={item.imagePath}
                            alt=""
                            style={{
                              position: 'absolute',
                              width: '113.41%',
                              height: '60.25%',
                              left: '-6.68%',
                              top: '-0.09%',
                              maxWidth: 'none',
                              display: 'block',
                            }}
                          />
                        </div>
                      </div>
                      <div
                        data-layer="Frame 2147227177"
                        style={{
                          width: 320,
                          flexDirection: 'column',
                          justifyContent: 'flex-start',
                          alignItems: 'flex-start',
                          gap: 8,
                          display: 'flex',
                        }}
                      >
                        <div
                          data-layer="Editor"
                          style={{
                            alignSelf: 'stretch',
                            height: 19,
                            color: 'var(--Purple-500, #4C22F4)',
                            fontSize: 16,
                            fontFamily: 'Pretendard, -apple-system, sans-serif',
                            fontWeight: 500,
                            lineHeight: '19.1px',
                            overflow: 'hidden',
                            whiteSpace: 'nowrap',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {item.editor}
                        </div>
                        <div
                          data-layer="Title"
                          style={{
                            alignSelf: 'stretch',
                            maxHeight: 84,
                            color: 'var(--Gray-800, #2D2D34)',
                            fontSize: 20,
                            fontFamily: 'Pretendard, -apple-system, sans-serif',
                            fontWeight: 600,
                            lineHeight: '28px',
                            overflow: 'hidden',
                          }}
                        >
                          {item.title}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Section 4: Most Relatable Reviews */}
          <div
            data-layer="Frame 2147227196"
            className="home-reviews-section"
            style={{
              width: '100%',
              height: '393px',
              boxSizing: 'border-box',
              padding: '50px 120px',
              background: '#F8F8FA',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'flex-start',
              alignItems: 'flex-start',
              overflow: 'hidden',
            }}
          >
            <div
              data-layer="Frame 2147227193"
              className="home-reviews-inner"
              style={{
                width: '1680px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'flex-start',
                alignItems: 'flex-start',
                gap: '24px',
              }}
            >
              <div
                data-layer="Frame 2147227205"
                style={{
                  width: '100%',
                  height: '39px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div
                  data-layer="Most Relatable Reviews"
                  style={{
                    color: '#2D2D34',
                    fontSize: '28px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    fontWeight: 600,
                    lineHeight: '39.2px',
                  }}
                >
                  Most Relatable Reviews
                </div>
              </div>

              {reviewsLoading ? (
                <div data-testid="loading-reviews-state" style={{ width: '100%', padding: '40px 0', color: '#898992', fontSize: '16px', fontFamily: 'Pretendard, -apple-system, sans-serif' }}>
                  Loading audience reviews...
                </div>
              ) : reviewsError ? (
                <div data-testid="error-reviews-state" style={{ width: '100%', padding: '40px 0', color: '#7A271A', fontSize: '16px', fontFamily: 'Pretendard, -apple-system, sans-serif', display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <span>{reviewsError}</span>
                  <button type="button" onClick={() => setRetryTrigger((prev) => prev + 1)} style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid #7A271A', background: 'none', color: '#7A271A', cursor: 'pointer', fontWeight: 600 }}>
                    Retry
                  </button>
                </div>
              ) : reviewItems.length === 0 ? (
                <div
                  data-testid="empty-reviews-state"
                  style={{
                    width: '100%',
                    padding: '40px 0',
                    color: '#898992',
                    fontSize: '16px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                  }}
                >
                  No audience reviews yet.
                </div>
              ) : (
                <div
                  data-layer="Frame 2147227192"
                  className="home-reviews-row"
                  style={{
                    width: '1680px',
                    height: '230px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '20px',
                  }}
                >
                  {reviewItems.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => navigate(item.destination)}
                      aria-label={`${item.filmTitle} review`}
                      data-layer="Frame 2147227187"
                      style={{
                        width: '405px',
                        height: '211px',
                        boxSizing: 'border-box',
                        background: '#FFFFFF',
                        borderRadius: '12px',
                        border: 'none',
                        cursor: 'pointer',
                        position: 'relative',
                        textAlign: 'left',
                        font: 'inherit',
                        margin: 0,
                        padding: 0,
                      }}
                    >
                      <div
                        data-layer="영화 제목"
                        style={{
                          position: 'absolute',
                          left: '30px',
                          top: '25px',
                          width: '345px',
                          height: '19px',
                          color: '#4C22F4',
                          fontSize: '16px',
                          fontFamily: 'Pretendard, -apple-system, sans-serif',
                          fontWeight: 500,
                          lineHeight: '19.1px',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {item.filmTitle}
                      </div>

                      {item.rating != null ? (
                        <div
                          data-layer="StarRating"
                          style={{
                            position: 'absolute',
                            left: '30px',
                            top: '60px',
                            width: '345px',
                            height: '24px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                          }}
                        >
                          <div style={{ display: 'flex', width: '120px', height: '24px' }}>
                            {[1, 2, 3, 4, 5].map((s) => (
                              <svg key={s} width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path
                                  d="M10.8471 2.33613C11.3187 1.38052 12.6813 1.38052 13.1529 2.33612L15.2276 6.53976C15.4148 6.91923 15.7769 7.18225 16.1956 7.2431L20.8346 7.91718C21.8892 8.07042 22.3103 9.36638 21.5472 10.1102L18.1904 13.3823C17.8873 13.6777 17.7491 14.1032 17.8206 14.5203L18.613 19.1406C18.7932 20.1909 17.6908 20.9918 16.7475 20.4959L12.5983 18.3145C12.2237 18.1176 11.7763 18.1176 11.4017 18.3145L7.25247 20.4959C6.30924 20.9918 5.20682 20.1909 5.38696 19.1406L6.1794 14.5203C6.25093 14.1032 6.11265 13.6777 5.80963 13.3823L2.45283 10.1102C1.68974 9.36638 2.11082 8.07042 3.16539 7.91718L7.80437 7.2431C8.22314 7.18225 8.58516 6.91923 8.77244 6.53976L10.8471 2.33613Z"
                                  fill={s <= item.rating! ? '#FED200' : '#F2F2F5'}
                                />
                              </svg>
                            ))}
                          </div>
                          <span
                            style={{
                              color: '#AFAFB8',
                              fontSize: '16px',
                              fontFamily: 'Pretendard, -apple-system, sans-serif',
                              fontWeight: 500,
                              lineHeight: '19.1px',
                            }}
                          >
                            {item.rating}
                          </span>
                        </div>
                      ) : null}

                      <div
                        data-layer="ReviewBody"
                        style={{
                          position: 'absolute',
                          left: '30px',
                          top: '96px',
                          width: '345px',
                          height: '84px',
                          color: '#2D2D34',
                          fontSize: '20px',
                          fontFamily: 'Pretendard, -apple-system, sans-serif',
                          fontWeight: 600,
                          lineHeight: '28px',
                          letterSpacing: '-0.3px',
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {item.body}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <section id="faq" className="home-faq-section" style={{ width: '100%', padding: '50px clamp(20px, 6.25vw, 120px)', boxSizing: 'border-box', background: '#fff' }}>
            <h2 style={{ fontSize: 28, fontWeight: 600, margin: '0 0 24px', color: '#2D2D34' }}>FAQ</h2>
            {[
              ['What can I do on RE:SCENE?', 'Explore movies, read scene interpretations and editorial articles, and share your own reviews. Log in to save films to your Wishlist and join interpretation discussions.'],
              ['How are spoilers handled?', 'Reviews and comments can be marked as containing spoilers. Potential spoilers are hidden until you choose to reveal them. User text is never rewritten by the spoiler check.'],
              ['Do I need an account?', 'You can browse without an account. Log in to write reviews, comment, like interpretations and reviews, or save films. Password recovery is not available yet.'],
            ].map(([question, answer]) => <details key={question} style={{ borderBottom: '1px solid #E6E6EA', padding: '18px 0' }}><summary style={{ cursor: 'pointer', fontSize: 16, fontWeight: 500 }}>{question}</summary><p style={{ color: '#777780', lineHeight: 1.7, marginBottom: 0 }}>{answer}</p></details>)}
          </section>

        </div>
      </div>
    </div>
  );
};
