import React, { useState, useEffect, useRef, useCallback } from 'react';
import { magazineApi } from '../services/apiClient';
import { SortOptions, articleSortOptions } from '../components/SortOptions';
import { compareRanking } from '../utils/contentRanking';
import { isVisualFixtureMode } from '../testing/useVisualFixture';
import { LoadingState, ErrorState, EmptyState } from '../components/FeedbackStates';
import {
  parseMagazineListResponse,
  MagazineCardViewModel,
} from './magazineViewModel';

interface MagazinePageProps {
  navigate: (path: string) => void;
}

export const MagazinePage: React.FC<MagazinePageProps> = ({ navigate }) => {
  // --------------------------------------------------------------------------
  // FIXTURE ON BRANCH (Strictly preserved Figma 1:1 test state)
  // --------------------------------------------------------------------------
  if (isVisualFixtureMode()) {
    return <FixtureMagazinePage navigate={navigate} />;
  }

  // --------------------------------------------------------------------------
  // FIXTURE OFF BRANCH (API integration with strict envelope & error handling)
  // --------------------------------------------------------------------------
  return <LiveMagazinePage navigate={navigate} />;
};

const LiveMagazinePage: React.FC<MagazinePageProps> = ({ navigate }) => {
  const [articles, setArticles] = useState<MagazineCardViewModel[]>([]);
  const [sort, setSort] = useState('latest');
  const [total, setTotal] = useState<number>(0);
  const [disclaimer, setDisclaimer] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<{ statusCode?: number; message: string } | null>(null);
  const [failedImageIds, setFailedImageIds] = useState<Set<string>>(new Set());

  const reqIdRef = useRef(0);

  const loadArticles = useCallback(async (currentReq: number) => {
    setLoading(true);
    setError(null);
    try {
      // Calls GET /api/v1/magazine?work_id=the-bat-whispers-1930
      const res = await magazineApi.listArticles();

      if (reqIdRef.current !== currentReq) return;

      const parsed = parseMagazineListResponse(res);
      if (parsed.kind === 'ERROR') {
        setArticles([]);
        setTotal(0);
        setDisclaimer(null);
        setError({ message: parsed.error });
      } else if (parsed.kind === 'EMPTY') {
        setArticles([]);
        setTotal(0);
        setDisclaimer(parsed.disclaimer);
        setError(null);
      } else {
        setArticles(parsed.articles);
        setTotal(parsed.total);
        setDisclaimer(parsed.disclaimer);
        setError(null);
      }
    } catch (err: any) {
      if (reqIdRef.current !== currentReq) return;
      setArticles([]);
      setTotal(0);
      setDisclaimer(null);
      if (err?.status === 403) {
        setError({
          statusCode: 403,
          message: 'Magazine feature is currently unavailable. (403 Forbidden)',
        });
      } else {
        setError({
          statusCode: err?.status,
          message: err?.message || 'Could not load editorial articles. Please try again.',
        });
      }
    } finally {
      if (reqIdRef.current === currentReq) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const currentReq = ++reqIdRef.current;
    loadArticles(currentReq);
    return () => {
      reqIdRef.current++;
    };
  }, [loadArticles]);

  const handleRetry = () => {
    const currentReq = ++reqIdRef.current;
    loadArticles(currentReq);
  };

  return (
    <div
      data-layer="매거진"
      data-testid="magazine-page"
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
      {/* Top Header & Sort Controls */}
      <div
        data-layer="Frame 2147227218"
        style={{
          alignSelf: 'stretch',
          height: 61,
          boxSizing: 'border-box',
          paddingLeft: 120,
          paddingRight: 120,
          paddingTop: 20,
          paddingBottom: 20,
          borderBottom: '1px var(--Gray-100, #F2F2F5) solid',
          justifyContent: 'space-between',
          alignItems: 'center',
          display: 'flex',
        }}
      >
        <div
          data-testid="magazine-article-count"
          data-layer="총 개수"
          style={{
            color: 'var(--Gray-800, #2D2D34)',
            fontSize: 18,
            fontFamily: 'Pretendard',
            fontWeight: '600',
            lineHeight: '21px',
          }}
        >
          Total {articles.length} articles
        </div>

        <SortOptions label="Sort articles" value={sort} onChange={setSort} options={articleSortOptions} />
      </div>

      {/* Disclaimer Banner */}
      {disclaimer && (
        <div
          data-testid="magazine-disclaimer-banner"
          style={{
            padding: '10px 120px',
            background: '#F8F9FA',
            color: '#6B6B75',
            fontSize: 13,
            fontFamily: 'Pretendard',
            borderBottom: '1px solid #EEEEEE',
          }}
        >
          ℹ️ {disclaimer}
        </div>
      )}

      {/* Main Content Area */}
      <div
        style={{
          alignSelf: 'stretch',
          padding: '40px 120px 80px 120px',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {loading && (
          <div data-testid="magazine-loading">
            <LoadingState message="Loading magazine articles..." />
          </div>
        )}

        {!loading && error && (
          <div
            data-testid={
              error.statusCode === 403
                ? 'magazine-disabled-state'
                : 'magazine-error-state'
            }
          >
            <ErrorState
              title={
                error.statusCode === 403
                  ? 'Feature Unavailable'
                  : 'Failed to Load Magazine'
              }
              message={error.message}
              statusCode={error.statusCode}
              onRetry={error.statusCode !== 403 ? handleRetry : undefined}
            />
          </div>
        )}

        {!loading && !error && articles.length === 0 && (
          <div data-testid="magazine-empty-state">
            <EmptyState
              title="No magazine articles found"
              message="There are currently no published analysis articles or rewatch guides."
            />
          </div>
        )}

        {!loading && !error && articles.length > 0 && (
          <div
            data-testid="magazine-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 320px))',
              gap: 20,
            }}
          >
            {[...articles].sort((a, b) => {
              return compareRanking(a, b, sort) || a.articleId.localeCompare(b.articleId);
            }).map((article, idx) => (
              <div
                key={article.articleId}
                data-testid={`magazine-card-${idx}`}
                data-layer={`Frame 214722717${8 + (idx % 5)}`}
                onClick={() =>
                  navigate(`/magazine/${encodeURIComponent(article.articleId)}`)
                }
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 20,
                  cursor: 'pointer',
                  width: '100%',
                  maxWidth: 320,
                }}
              >
                {/* 320x232 Thumbnail Slot matching Figma Frame Rectangle 240655222 */}
                <div
                  data-layer="Rectangle 240655222"
                  data-testid={`magazine-card-thumbnail-${idx}`}
                  style={{
                    width: '100%',
                    height: 232,
                    background: '#D9D9D9',
                    borderRadius: 20,
                    overflow: 'hidden',
                    position: 'relative',
                  }}
                >
                  {article.heroImage && !failedImageIds.has(article.articleId) ? (
                    <img
                      src={article.heroImage}
                      alt={article.title}
                      loading="lazy"
                      decoding="async"
                      onError={() => {
                        setFailedImageIds((prev) => new Set(prev).add(article.articleId));
                      }}
                      style={{
                        width: '100%',
                        height: '100%',
                        aspectRatio: '320 / 232',
                        objectFit: 'cover',
                        display: 'block',
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        width: '100%',
                        height: '100%',
                        background: '#E9E8E6',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#898992',
                        fontSize: 14,
                        fontFamily: 'Pretendard',
                      }}
                    >
                      Photo unavailable
                    </div>
                  )}
                  {article.isSpoilerLocked && (
                    <span
                      data-testid={`magazine-card-lock-${idx}`}
                      style={{
                        position: 'absolute',
                        top: 12,
                        right: 12,
                        fontSize: 12,
                        color: '#D97706',
                        background: 'rgba(255, 255, 255, 0.92)',
                        padding: '3px 8px',
                        borderRadius: 9999,
                        fontWeight: 600,
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                      }}
                    >
                      🔒 Spoiler Protected
                    </span>
                  )}
                </div>

                {/* Text Block: Category + Title */}
                <div
                  data-layer="Frame 2147227289"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    width: '100%',
                  }}
                >
                  <div
                    data-layer="카테고리"
                    data-testid={`magazine-card-category-${idx}`}
                    style={{
                      color: '#4C22F4',
                      fontSize: 16,
                      fontFamily: 'Pretendard',
                      fontWeight: 600,
                      lineHeight: '20px',
                    }}
                  >
                    {article.articleType || 'Article'}
                  </div>
                  <div
                    data-layer="제목"
                    data-testid={`magazine-card-title-${idx}`}
                    style={{
                      color: 'var(--Gray-800, #2D2D34)',
                      fontSize: 18,
                      fontFamily: 'Pretendard',
                      fontWeight: 600,
                      lineHeight: '24px',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {article.title}
                  </div>
                  {article.authorAlias && (
                    <div
                      data-testid={`magazine-card-author-${idx}`}
                      style={{
                        fontSize: 13,
                        color: '#898992',
                        fontFamily: 'Pretendard',
                      }}
                    >
                      {article.authorAlias}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Fixture ON implementation - preserved 1:1
 */
const FixtureMagazinePage: React.FC<MagazinePageProps> = ({ navigate }) => {
  const [sort, setSort] = useState<'latest' | 'popular' | 'views'>('latest');

  // 4 rows of 5 cards = 20 cards matching 1:1 Figma Frame 9 (15:35295)
  const rows = [
    [0, 1, 2, 3, 4],
    [5, 6, 7, 8, 9],
    [10, 11, 12, 13, 14],
    [15, 16, 17, 18, 19],
  ];

  return (
    <div
      data-layer="매거진"
      style={{
        width: 1920,
        position: 'relative',
        background: 'var(--Gray-0, white)',
        flexDirection: 'column',
        display: 'flex',
      }}
    >
      <div
        data-layer="Frame 2147227218"
        style={{
          alignSelf: 'stretch',
          height: 61,
          boxSizing: 'border-box',
          paddingLeft: 120,
          paddingRight: 120,
          paddingTop: 20,
          paddingBottom: 20,
          borderBottom: '1px var(--Gray-100, #F2F2F5) solid',
          justifyContent: 'space-between',
          alignItems: 'center',
          display: 'inline-flex',
        }}
      >
        <div
          data-layer="총 29개"
          style={{
            color: 'var(--Gray-800, #2D2D34)',
            fontSize: 18,
            fontFamily: 'Pretendard',
            fontWeight: '600',
            lineHeight: '21px',
            wordWrap: 'break-word',
          }}
        >
          총 29개
        </div>
        <div
          data-layer="Frame 2147227219"
          style={{
            justifyContent: 'flex-start',
            alignItems: 'center',
            gap: 10,
            display: 'flex',
          }}
        >
          <div
            onClick={() => setSort('latest')}
            data-layer="최신순"
            style={{
              color:
                sort === 'latest'
                  ? 'var(--Gray-800, #2D2D34)'
                  : 'var(--Gray-500, #898992)',
              fontSize: 16,
              fontFamily: 'Pretendard',
              fontWeight: '400',
              lineHeight: '20px',
              wordWrap: 'break-word',
              cursor: 'pointer',
            }}
          >
            최신순
          </div>
          <div
            onClick={() => setSort('popular')}
            data-layer="인기순"
            style={{
              color:
                sort === 'popular'
                  ? 'var(--Gray-800, #2D2D34)'
                  : 'var(--Gray-500, #898992)',
              fontSize: 16,
              fontFamily: 'Pretendard',
              fontWeight: '400',
              lineHeight: '20px',
              wordWrap: 'break-word',
              cursor: 'pointer',
            }}
          >
            인기순
          </div>
          <div
            onClick={() => setSort('views')}
            data-layer="조회수"
            style={{
              color:
                sort === 'views'
                  ? 'var(--Gray-800, #2D2D34)'
                  : 'var(--Gray-500, #898992)',
              fontSize: 16,
              fontFamily: 'Pretendard',
              fontWeight: '400',
              lineHeight: '20px',
              wordWrap: 'break-word',
              cursor: 'pointer',
            }}
          >
            조회수
          </div>
        </div>
      </div>

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
          data-layer="Frame 2147227195"
          style={{
            alignSelf: 'stretch',
            paddingLeft: 120,
            paddingRight: 120,
            paddingTop: 41,
            paddingBottom: 36,
            flexDirection: 'column',
            justifyContent: 'flex-start',
            alignItems: 'flex-start',
            display: 'flex',
          }}
        >
          <div
            data-layer="Frame 2147227288"
            style={{
              alignSelf: 'stretch',
              flexDirection: 'column',
              justifyContent: 'flex-start',
              alignItems: 'flex-start',
              gap: 20,
              display: 'flex',
            }}
          >
            {rows.map((row, rIdx) => (
              <div
                key={rIdx}
                data-layer={`Frame 214722718${rIdx}`}
                style={{
                  alignSelf: 'stretch',
                  height: 337,
                  boxSizing: 'border-box',
                  justifyContent: 'flex-start',
                  alignItems: 'flex-start',
                  gap: 20,
                  display: 'inline-flex',
                }}
              >
                {row.map((itemIdx) => (
                  <div
                    key={itemIdx}
                    onClick={() => navigate('/magazine/mag_001')}
                    data-layer={`Frame 214722717${8 + (itemIdx % 5)}`}
                    style={{
                      flex: '1 1 0',
                      alignSelf: 'stretch',
                      flexDirection: 'column',
                      justifyContent: 'flex-start',
                      alignItems: 'flex-start',
                      gap: 20,
                      display: 'inline-flex',
                      cursor: 'pointer',
                    }}
                  >
                    <div
                      data-layer="Rectangle 240655222"
                      style={{
                        alignSelf: 'stretch',
                        height: 232,
                        background: '#D9D9D9',
                        borderRadius: 12,
                      }}
                    />
                    <div
                      data-layer="Frame 2147227177"
                      style={{
                        flexDirection: 'column',
                        justifyContent: 'flex-start',
                        alignItems: 'flex-start',
                        gap: 8,
                        display: 'flex',
                      }}
                    >
                      <div
                        data-layer="카테고리"
                        style={{
                          alignSelf: 'stretch',
                          justifyContent: 'center',
                          display: 'flex',
                          flexDirection: 'column',
                          color: 'var(--Purple-500, #4C22F4)',
                          fontSize: 16,
                          fontFamily: 'Pretendard',
                          fontWeight: '500',
                          wordWrap: 'break-word',
                        }}
                      >
                        카테고리
                      </div>
                      <div
                        data-layer="제목을 2줄로 구성해서 적어주세요."
                        style={{
                          justifyContent: 'center',
                          display: 'flex',
                          flexDirection: 'column',
                          color: 'var(--Gray-800, #2D2D34)',
                          fontSize: 18,
                          fontFamily: 'Pretendard',
                          fontWeight: '600',
                          lineHeight: '27px',
                          wordWrap: 'break-word',
                        }}
                      >
                        제목을 2줄로
                        <br />
                        구성해서 적어주세요.
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
