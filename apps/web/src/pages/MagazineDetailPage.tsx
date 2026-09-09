import React, { useState, useEffect, useRef, useCallback } from 'react';
import { magazineApi, communityApi } from '../services/apiClient';
import { recordPageView } from '../utils/pageViews';
import { useAuth } from '../context/AuthContext';
import { WriteAccessGate } from '../components/WriteAccessGate';
import { isVisualFixtureMode } from '../testing/useVisualFixture';
import { LoadingState, ErrorState } from '../components/FeedbackStates';
import {
  parseMagazineDetailResponse,
  isValidUuid,
  MagazineDetailResult,
  VisibleMagazineArticleViewModel,
} from './magazineViewModel';
import proofLikeDefaultSvg from '../assets/figma/proof-like-default.svg';
import proofLikeSelectedSvg from '../assets/figma/proof-like-selected.svg';
import proofCommentSvg from '../assets/figma/proof-comment.svg';
import proofShareSvg from '../assets/figma/proof-share.svg';
import magazineHeroImg from '../assets/figma/magazine-mystery-viewings.png';

interface MagazineDetailPageProps {
  articleId?: string;
  navigate?: (path: string) => void;
}

/**
 * Pinned Figma 553:7055 Visual Sample (Short Magazine Detail).
 * Strictly isolated for visual fixture mode.
 */
export const FIGMA_553_7055_SAMPLE = {
  title: 'How Many Viewings Does It Take to Fully Appreciate a Mystery Movie?',
  publishedAt: '2026.06.12',
  author: 'MJay, Culture Editor',
  introParagraphs: [
    'A great mystery movie rarely ends when the credits begin to roll.',
    'The first viewing is about uncertainty. We follow the investigation, question every character, and search for clues while the film carefully directs—or misdirects—our attention.',
    'The second viewing offers an entirely different experience. Once we know the truth, suspicious pauses, unusual camera angles, and seemingly harmless dialogue begin to reveal their purpose.',
    'What first appeared to be background decoration may become a vital clue. A character’s awkward reaction may suddenly feel like a confession hidden in plain sight.',
    'By the third viewing, the mystery is no longer only about identifying the culprit. We begin to examine how the director controlled our expectations through editing, sound, color, and perspective.',
    'Some viewers believe that knowing the answer removes the excitement. Yet a carefully constructed mystery often becomes more rewarding after its secret has been revealed.',
    'The best twists do not simply surprise us—they invite us to return and discover that the truth was visible all along.',
  ],
  heroImage: magazineHeroImg,
  outroParagraphs: [
    'So, how many viewings does it take to fully appreciate a mystery movie?',
    'Perhaps the answer is three: one to be deceived, one to uncover the clues, and one to appreciate how beautifully the deception was designed.',
  ],
  likesCount: 293,
  commentCount: 16,
};

interface CommonArticlePresentationProps {
  articleId?: string;
  title: string;
  publishedAt?: string | null;
  author?: string | null;
  dek?: string | null;
  isSample?: boolean;
  sampleIntroParagraphs?: string[];
  sampleHeroImage?: string;
  sampleOutroParagraphs?: string[];
  introParagraphs?: string[];
  paragraphs?: string[];
  heroImage?: string;
  outroParagraphs?: string[];
  sampleLikes?: number;
  sampleComments?: number;
  bodySections?: VisibleMagazineArticleViewModel['bodySections'];
  evidenceRefs?: VisibleMagazineArticleViewModel['evidenceRefs'];
  navigate: (path: string) => void;
}

/**
 * Shared article presentation between Fixture sample and Live VISIBLE view model.
 * Adheres strictly to Figma Frame 2147227195 (node 553:7055).
 */
export const CommonArticlePresentation: React.FC<CommonArticlePresentationProps> = ({
  articleId,
  title,
  publishedAt,
  author,
  dek,
  isSample = false,
  sampleIntroParagraphs,
  sampleHeroImage,
  sampleOutroParagraphs,
  introParagraphs,
  paragraphs,
  heroImage,
  outroParagraphs,
  bodySections,
  evidenceRefs,
  navigate,
}) => {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const canWrite = () => {
    if (authLoading) return false;
    if (!isAuthenticated) { navigate?.('/login'); return false; }
    return true;
  };
  const effectiveIntro = isSample
    ? sampleIntroParagraphs
    : (introParagraphs && introParagraphs.length > 0 ? introParagraphs : paragraphs);
  const rawHero = isSample ? sampleHeroImage : heroImage;
  const effectiveHero = rawHero && rawHero.includes('magazine-mystery-viewings') ? magazineHeroImg : rawHero;
  const effectiveOutro = isSample ? sampleOutroParagraphs : outroParagraphs;

  // Byline dek dedup: don't render redundant dek if it repeats intro paragraph
  const isDekDuplicate = Boolean(
    dek && effectiveIntro?.some((p) => p.trim().startsWith(dek.trim()) || dek.trim().startsWith(p.trim().slice(0, 40)))
  );
  const showDek = Boolean(dek && !isDekDuplicate);

  // Share state
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [manualCopyUrl, setManualCopyUrl] = useState<string | null>(null);
  const copyTimerRef = useRef<any>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleShare = async () => {
    const canonicalUrl = `${window.location.origin}/magazine/${encodeURIComponent(articleId || '')}`;
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(canonicalUrl);
        setCopyStatus('copied');
        setManualCopyUrl(null);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setCopyStatus('idle'), 2500);
      } else {
        throw new Error('Clipboard API unavailable');
      }
    } catch {
      setCopyStatus('failed');
      setManualCopyUrl(canonicalUrl);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopyStatus('idle'), 6000);
    }
  };

  return (
    <div
      data-layer="매거진 - 상세페이지"
      data-testid="magazine-detail-page"
      className="magazine-detail-wrapper"
    >
      <button
        type="button"
        className="magazine-skip-back"
        data-testid="magazine-back-button"
        onClick={() => navigate('/magazine')}
      >
        ← Back to Magazine
      </button>

      <div
        className="magazine-detail-panel"
        data-layer="Frame 2147227195"
        data-testid="magazine-detail-panel"
      >
        <div
          data-layer="Frame 2147227288"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 28,
            width: '100%',
          }}
        >
          <header className="magazine-detail-header" data-layer="Frame 2147227290">
            <div className="magazine-detail-title-row" data-layer="Frame 2147227289">
              <h1
                className="magazine-detail-title"
                data-layer={isSample ? title : undefined}
                data-testid="magazine-title"
              >
                {title}
              </h1>
              {publishedAt && (
                <span
                  className="magazine-detail-date"
                  data-layer={isSample ? publishedAt : undefined}
                  data-testid="magazine-date"
                >
                  {publishedAt}
                </span>
              )}
            </div>

            <div
              className="magazine-detail-byline"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              {author && (
                <p
                  className="magazine-detail-author"
                  data-layer={isSample ? author : undefined}
                  data-testid="magazine-author"
                  style={{ margin: 0, fontWeight: 500 }}
                >
                  {author}
                </p>
              )}
            </div>

            {showDek && (
              <p
                className="magazine-detail-dek"
                data-testid="magazine-dek"
                style={{
                  margin: '8px 0 0 0',
                  color: '#6B6B75',
                  fontSize: 15,
                  fontStyle: 'italic',
                }}
              >
                {dek}
              </p>
            )}
          </header>

          {effectiveIntro && effectiveIntro.length > 0 && (
            <div
              className="magazine-detail-paragraphs"
              data-layer="A great mystery movie rarely ends when the credits begin to roll..."
              data-testid={isSample ? "magazine-sample-intro" : "magazine-editorial-intro"}
            >
              {effectiveIntro.map((p, idx) => (
                <p key={idx} className="magazine-detail-paragraph">
                  {p}
                </p>
              ))}
            </div>
          )}

          {effectiveHero && (
            <div
              className="magazine-detail-hero"
              data-layer="Rectangle 240655222"
              data-testid="magazine-hero-image"
            >
              <img
                src={effectiveHero}
                alt={title}
                className="magazine-detail-hero-img"
              />
            </div>
          )}

          {effectiveOutro && effectiveOutro.length > 0 && (
            <div
              className="magazine-detail-paragraphs"
              data-layer="So, how many viewings does it take to fully appreciate a mystery movie?..."
              data-testid={isSample ? "magazine-sample-outro" : "magazine-editorial-outro"}
            >
              {effectiveOutro.map((p, idx) => (
                <p key={idx} className="magazine-detail-paragraph">
                  {p}
                </p>
              ))}
            </div>
          )}

          {!isSample && (
            <>
              {bodySections && bodySections.length > 0 && (
                <div
                  data-testid="magazine-sections"
                  className="magazine-live-sections"
                >
                  {bodySections.map((sec, idx) => (
                    <div
                      key={sec.key || idx}
                      data-testid={`magazine-section-${sec.key || idx}`}
                      className="magazine-live-section"
                      style={{ marginBottom: 24 }}
                    >
                      {sec.title && (
                        <h2 className="magazine-section-heading">{sec.title}</h2>
                      )}
                      <p className="magazine-section-body">{sec.content}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Verified Evidence References */}
              {evidenceRefs && evidenceRefs.length > 0 && (
                <div
                  data-testid="magazine-evidence-links"
                  className="magazine-evidence-box"
                >
                  <h3 className="magazine-evidence-title">
                    Linked Forensic Evidence
                  </h3>
                  <div className="magazine-evidence-list">
                    {evidenceRefs.map((ev, idx) => (
                      <div
                        key={ev.evidenceId || idx}
                        data-testid={`magazine-evidence-${idx}`}
                        className="magazine-evidence-item"
                        style={{
                          cursor: ev.evidenceId ? 'pointer' : 'default',
                        }}
                        onClick={() => {
                          if (ev.evidenceId) {
                            navigate(`/proofs/${encodeURIComponent(ev.evidenceId)}`);
                          }
                        }}
                      >
                        <span className="magazine-evidence-label">
                          {ev.evidenceType ? `[${ev.evidenceType}] ` : ''}{ev.evidenceId}
                        </span>
                        {(ev.timestampFormatted || ev.timestampMs !== null) && (
                          <span className="magazine-evidence-ts">
                            {ev.timestampFormatted || `${Math.floor((ev.timestampMs ?? 0) / 60000)}:${String(Math.floor(((ev.timestampMs ?? 0) % 60000) / 1000)).padStart(2, '0')}`}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          <div
            className="magazine-detail-reactions"
            data-layer="Frame 2147227304"
            data-testid="magazine-reactions-row"
          >
            <button
              type="button"
              className="magazine-reaction-item"
              data-layer="ShareButton"
              data-testid="magazine-reaction-share"
              onClick={handleShare}
              aria-label="Share article link"
              style={{
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <img
                src={proofShareSvg}
                alt=""
                className="magazine-reaction-icon"
                aria-hidden="true"
              />
              <span className="magazine-reaction-text">
                {copyStatus === 'copied'
                  ? 'Link copied!'
                  : copyStatus === 'failed'
                  ? 'Could not copy link'
                  : 'Share'}
              </span>
            </button>
          </div>

          {manualCopyUrl && (
            <div
              style={{
                padding: '8px 12px',
                background: '#F8F9FA',
                border: '1px solid #EEEEEE',
                borderRadius: 6,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <span style={{ fontSize: 13, color: '#6B6B75' }}>Copy URL:</span>
              <input
                type="text"
                readOnly
                value={manualCopyUrl}
                onFocus={(e) => e.target.select()}
                style={{
                  flex: 1,
                  padding: '4px 8px',
                  fontSize: 13,
                  border: '1px solid #D4D4DA',
                  borderRadius: 4,
                }}
              />
            </div>
          )}


        </div>
      </div>
    </div>
  );
};

/**
 * Fixture Mode component — renders isolated Figma 553:7055 sample via common presentation.
 */
const FixtureMagazineDetailPage: React.FC<{ navigate?: (path: string) => void }> = ({
  navigate = () => {},
}) => {
  return (
    <CommonArticlePresentation
      title={FIGMA_553_7055_SAMPLE.title}
      publishedAt={FIGMA_553_7055_SAMPLE.publishedAt}
      author={FIGMA_553_7055_SAMPLE.author}
      isSample={true}
      sampleIntroParagraphs={FIGMA_553_7055_SAMPLE.introParagraphs}
      sampleHeroImage={FIGMA_553_7055_SAMPLE.heroImage}
      sampleOutroParagraphs={FIGMA_553_7055_SAMPLE.outroParagraphs}
      sampleLikes={FIGMA_553_7055_SAMPLE.likesCount}
      sampleComments={FIGMA_553_7055_SAMPLE.commentCount}
      navigate={navigate}
    />
  );
};

/**
 * Live Mode component — fetches real UUID article and consumes VisibleMagazineArticleViewModel.
 */
const LiveMagazineDetailPage: React.FC<MagazineDetailPageProps> = ({
  articleId,
  navigate = () => {},
}) => {
  const [result, setResult] = useState<MagazineDetailResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<{ statusCode?: number; message: string } | null>(null);

  const reqIdRef = useRef(0);
  const activeIdRef = useRef<string | null>(null);

  const loadArticle = useCallback(
    async (rawArticleId: string | undefined, currentReq: number) => {
      // 1. Single URL decode
      let targetId: string | null = null;
      try {
        targetId = rawArticleId ? decodeURIComponent(rawArticleId).trim() : null;
      } catch {
        targetId = null;
      }

      // 2. Validate UUID format before calling API
      if (!targetId || !isValidUuid(targetId)) {
        if (reqIdRef.current === currentReq) {
          setResult(null);
          setError({
            statusCode: 404,
            message: 'Invalid article identifier. (404 Not Found)',
          });
          setLoading(false);
        }
        return;
      }

      activeIdRef.current = targetId;
      setResult(null);
      setError(null);
      setLoading(true);

      try {
        // Single URI encode for outgoing network path
        const res = await magazineApi.getArticle(encodeURIComponent(targetId));

        if (reqIdRef.current !== currentReq || activeIdRef.current !== targetId) {
          return;
        }

        const parsed = parseMagazineDetailResponse(res, targetId);
        if (parsed.kind === 'ERROR') {
          setError({ statusCode: parsed.statusCode || 500, message: parsed.error });
          setResult(null);
        } else {
          setResult(parsed);
          if (parsed.kind === 'VISIBLE') void recordPageView('magazine', targetId);
          setError(null);
        }
      } catch (err: any) {
        if (reqIdRef.current !== currentReq || activeIdRef.current !== targetId) {
          return;
        }
        setResult(null);
        if (err?.status === 403) {
          setError({
            statusCode: 403,
            message: 'Magazine feature is currently disabled. (403 Forbidden)',
          });
        } else if (err?.status === 404) {
          setError({
            statusCode: 404,
            message: 'Magazine article not found. (404 Not Found)',
          });
        } else {
          setError({
            statusCode: err?.status || 500,
            message: err?.message || 'Failed to load article.',
          });
        }
      } finally {
        if (reqIdRef.current === currentReq) {
          setLoading(false);
        }
      }
    },
    []
  );

  useEffect(() => {
    const currentReq = ++reqIdRef.current;
    loadArticle(articleId, currentReq);
    return () => {
      reqIdRef.current++;
    };
  }, [articleId, loadArticle]);

  const handleRetry = () => {
    const currentReq = ++reqIdRef.current;
    loadArticle(articleId, currentReq);
  };

  // Loading State
  if (loading) {
    return (
      <div
        data-layer="매거진 - 상세페이지"
        data-testid="magazine-detail-page"
        className="magazine-detail-wrapper"
      >
        <button
          type="button"
          className="magazine-visible-back"
          data-testid="magazine-back-button"
          onClick={() => navigate('/magazine')}
        >
          ← Back to Magazine
        </button>
        <div data-testid="magazine-loading">
          <LoadingState message="Retrieving article text and evidence catalog..." />
        </div>
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div
        data-layer="매거진 - 상세페이지"
        data-testid="magazine-detail-page"
        className="magazine-detail-wrapper"
      >
        <button
          type="button"
          className="magazine-visible-back"
          data-testid="magazine-back-button"
          onClick={() => navigate('/magazine')}
        >
          ← Back to Magazine
        </button>
        <div
          data-testid={
            error.statusCode === 404
              ? 'magazine-not-found-state'
              : error.statusCode === 403
              ? 'magazine-disabled-state'
              : 'magazine-error-state'
          }
        >
          <ErrorState
            title={
              error.statusCode === 404
                ? 'Article Not Found'
                : error.statusCode === 403
                ? 'Feature Unavailable'
                : 'Failed to Load Article'
            }
            message={error.message}
            statusCode={error.statusCode}
            onRetry={
              error.statusCode !== 404 && error.statusCode !== 403
                ? handleRetry
                : undefined
            }
          />
        </div>
      </div>
    );
  }

  // Protected State (Strict Epistemic Isolation)
  if (result?.kind === 'PROTECTED') {
    return (
      <div
        data-layer="매거진 - 상세페이지"
        data-testid="magazine-detail-page"
        className="magazine-detail-wrapper"
      >
        <button
          type="button"
          className="magazine-visible-back"
          data-testid="magazine-back-button"
          onClick={() => navigate('/magazine')}
        >
          ← Back to Magazine
        </button>

        <div
          data-testid="magazine-protected-container"
          className="magazine-protected-panel"
        >
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span
              data-testid="magazine-spoiler-badge"
              className="magazine-protected-spoiler-badge"
            >
              🔒 SPOILER PROTECTED
            </span>
            {result.article.articleType && (
              <span className="magazine-badge-type">
                {result.article.articleType}
              </span>
            )}
          </div>

          <h1
            data-testid="magazine-title"
            className="magazine-detail-title"
          >
            {result.article.title}
          </h1>

          {result.article.dek && (
            <p
              data-testid="magazine-dek"
              className="magazine-detail-dek"
            >
              {result.article.dek}
            </p>
          )}

          <div
            data-testid="magazine-protected-notice"
            className="magazine-protected-notice-box"
          >
            🔒 This article is spoiler-protected. The full text and forensic evidence links will unlock once you reach this reveal in the film.
          </div>

          <div
            data-testid="magazine-metadata"
            className="magazine-protected-metadata"
          >
            {result.article.authorAlias && (
              <span>Author: {result.article.authorAlias}</span>
            )}
            {result.article.isSynthetic === true && (
              <span data-testid="magazine-disclosure">
                {result.article.aiDisclosure || 'AI Analysis Demo'}
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Visible State (Common Article Presentation)
  if (result?.kind === 'VISIBLE') {
    return (
      <CommonArticlePresentation
        articleId={result.article.articleId}
        title={result.article.title}
        publishedAt={result.article.publishedAtFormatted || result.article.publishedAt}
        author={result.article.authorAlias}
        dek={result.article.dek}
        isSample={false}
        introParagraphs={result.article.introParagraphs}
        paragraphs={result.article.paragraphs}
        heroImage={result.article.heroImage || undefined}
        outroParagraphs={result.article.outroParagraphs}
        bodySections={result.article.bodySections}
        evidenceRefs={result.article.evidenceRefs}
        navigate={navigate}
      />
    );
  }

  return null;
};

export const MagazineDetailPage: React.FC<MagazineDetailPageProps> = ({
  articleId,
  navigate = () => {},
}) => {
  if (isVisualFixtureMode()) {
    return <FixtureMagazineDetailPage navigate={navigate} />;
  }

  return <LiveMagazineDetailPage articleId={articleId} navigate={navigate} />;
};

export default MagazineDetailPage;
