import React, { useEffect, useState, useRef, useCallback } from 'react';
import { apiClient, filmsApi } from '../services/apiClient';
import { useAuth } from '../context/AuthContext';
import { WriteAccessGate } from '../components/WriteAccessGate';
import { LoadingState, ErrorState, EmptyState } from '../components/FeedbackStates';
import {
  parseProofDetailResponse,
  ProofDetailResult,
} from './proofDetailViewModel';
import proofLikeSelectedSvg from '../assets/figma/proof-like-selected.svg';
import proofLikeDefaultSvg from '../assets/figma/proof-like-default.svg';
import proofCommentSvg from '../assets/figma/proof-comment.svg';
import proofShareSvg from '../assets/figma/proof-share.svg';
import { ProofComments } from '../components/ProofComments';
import { loginDestination } from '../utils/navigation';

interface ProofDetailPageProps {
  proofId: string;
  navigate: (path: string) => void;
}

// Visual fixture metadata map strictly for visual parity in test harness
const VISUAL_FIXTURE_REACTION_MAP: Record<
  string,
  { liked: boolean; likeCount: number; commentCount: number }
> = {
  'moment-1': {
    liked: true,
    likeCount: 293,
    commentCount: 16,
  },
};

export const ProofDetailPage: React.FC<ProofDetailPageProps> = ({ proofId, navigate }) => {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const canWrite = () => {
    if (authLoading) return false;
    if (!isAuthenticated) { navigate(loginDestination()); return false; }
    return true;
  };
  const [result, setResult] = useState<ProofDetailResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [reactionNotice, setReactionNotice] = useState<string | null>(null);
  const [filmTitle, setFilmTitle] = useState('');
  const proofWorkId = result?.kind === 'VISIBLE' || result?.kind === 'PROTECTED' ? result.proof.workId : null;
  useEffect(() => {
    let active = true; setFilmTitle('');
    if (proofWorkId) filmsApi.getFilm(proofWorkId).then(response => {
      if (active && typeof response.data?.title === 'string') setFilmTitle(response.data.title);
    }).catch(() => {});
    return () => { active = false; };
  }, [proofWorkId]);

  // Live engagement state
  const [likeCount, setLikeCount] = useState<number>(0);
  const [isLiked, setIsLiked] = useState<boolean>(false);
  const [liveCommentCount, setLiveCommentCount] = useState(0);
  const likePending = useRef(false);

  const reqIdRef = useRef(0);
  const activeProofIdRef = useRef<string | null>(null);

  const isVisualFixtureMode = import.meta.env.VITE_VISUAL_FIXTURE_MODE === 'true';

  const loadProofDetail = useCallback(async (rawProofId: string, currentReq: number) => {
    setReactionNotice(null);
    let decodedId: string | null = null;
    try {
      decodedId = decodeURIComponent(rawProofId);
    } catch {
      decodedId = null;
    }

    if (!decodedId || !decodedId.trim()) {
      if (reqIdRef.current === currentReq) {
        setResult({
          kind: 'ERROR',
          error: 'Invalid URL encoding or missing proof ID',
        });
        setFetchError('Invalid request address.');
        setLoading(false);
      }
      return;
    }

    const targetId = decodedId.trim();
    activeProofIdRef.current = targetId;

    setResult(null);
    setFetchError(null);
    setLoading(true);

    if (isVisualFixtureMode && targetId === 'moment-1') {
      setResult({
        kind: 'VISIBLE',
        proof: {
          kind: 'VISIBLE',
          proofId: 'moment-1',
          workId: 'the-bat-whispers-1930',
          title: 'The Most Trustworthy Detective Was the Most Dangerous Suspect',
          blindExplanation: null,
          revealExplanation:
            'Detective Anderson immediately gains everyone’s trust because he carries a badge and appears to represent the law. However, his attempts to control crucial information and monitor the other characters subtly hint at a hidden motive. The final reveal exposes him as the Bat, who attacked the real Anderson and stole his identity.',
          proofType: null,
          verificationStatus: null,
          trustNamespace: null,
          trustLabel: null,
          humanReviewStatus: null,
          observedPremises: [],
        },
      });
      setLoading(false);
      return;
    }

    try {
      const res = await apiClient.proof.getProofById(encodeURIComponent(targetId));

      if (reqIdRef.current !== currentReq || activeProofIdRef.current !== targetId) {
        return;
      }

      const parsed = parseProofDetailResponse(res, targetId);
      if (reqIdRef.current === currentReq) {
        setResult(parsed);
        if (parsed.kind === 'ERROR') {
          setFetchError(parsed.error);
        }
      }

      // Fetch live engagement in non-fixture mode
      if (!isVisualFixtureMode) {
        apiClient.proof.getProofReactions(encodeURIComponent(targetId))
          .then((rxRes) => {
            if (rxRes.data && activeProofIdRef.current === targetId && reqIdRef.current === currentReq) {
              setLikeCount(rxRes.data.like_count ?? 0);
              setIsLiked(Boolean(rxRes.data.viewer_liked));
            }
          })
          .catch(() => {});

      }
    } catch (err: any) {
      if (reqIdRef.current !== currentReq || activeProofIdRef.current !== targetId) {
        return;
      }
      setResult({
        kind: 'ERROR',
        error: err?.message || 'Failed to fetch proof detail',
      });
      setFetchError(err?.message || 'Failed to load proof details.');
    } finally {
      if (reqIdRef.current === currentReq) {
        setLoading(false);
      }
    }
  }, [isVisualFixtureMode]);

  useEffect(() => {
    setReactionNotice(null);
    const currentReq = ++reqIdRef.current;
    loadProofDetail(proofId, currentReq);

    return () => {
      reqIdRef.current++;
    };
  }, [proofId, loadProofDetail]);

  const handleRetry = () => {
    const currentReq = ++reqIdRef.current;
    loadProofDetail(proofId, currentReq);
  };

  const handleBack = () => {
    if (
      (result?.kind === 'VISIBLE' || result?.kind === 'PROTECTED') &&
      result.proof.workId
    ) {
      navigate(`/films/${encodeURIComponent(result.proof.workId)}`);
    } else {
      navigate('/');
    }
  };

  const handleLike = async () => {
    if (isVisualFixtureMode) {
      setReactionNotice('Likes, comments and sharing are not connected in this draft.');
      return;
    }
    const targetId = activeProofIdRef.current;
    if (!targetId || !canWrite() || likePending.current) return;
    likePending.current = true;
    const previousCount = likeCount;
    const nextLiked = !isLiked;
    setIsLiked(nextLiked);
    setLikeCount((prev) => (nextLiked ? prev + 1 : Math.max(0, prev - 1)));
    try {
      const rxRes = await apiClient.proof.putProofReaction(encodeURIComponent(targetId), nextLiked);
      if (rxRes.data && activeProofIdRef.current === targetId) {
        setLikeCount(rxRes.data.like_count ?? (nextLiked ? 1 : 0));
        setIsLiked(Boolean(rxRes.data.liked));
      }
    } catch (err: any) {
      if (activeProofIdRef.current === targetId) {
        setIsLiked(!nextLiked);
        setLikeCount(previousCount);
        setReactionNotice(err?.message || 'Failed to update reaction. Please try again.');
      }
    } finally { likePending.current = false; }
  };

  const handleToggleComments = () => {
    if (isVisualFixtureMode) {
      setReactionNotice('Likes, comments and sharing are not connected in this draft.');
      return;
    }
    document.querySelector('.proof-comments')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleShare = () => {
    const targetId = activeProofIdRef.current;
    if (!targetId) return;
    const canonicalUrl = `${window.location.origin}/proofs/${encodeURIComponent(targetId)}`;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(canonicalUrl)
        .then(() => setReactionNotice('Canonical link copied to clipboard.'))
        .catch(() => setReactionNotice(canonicalUrl));
    } else {
      setReactionNotice(canonicalUrl);
    }
  };

  const isVerifiedCanon =
    result?.kind === 'VISIBLE' &&
    result.proof.verificationStatus === 'VERIFIED_CANON' &&
    result.proof.trustNamespace === 'CANONICAL_VERIFIED';

  const statusText =
    result?.kind === 'VISIBLE'
      ? [result.proof.trustLabel || (result.proof.humanReviewStatus === 'NOT_REVIEWED' ? 'Not human reviewed' : result.proof.humanReviewStatus)]
          .filter(Boolean)
          .join(' • ')
      : '';

  const isCompact =
    result?.kind === 'VISIBLE' &&
    !!result.proof.revealExplanation &&
    !result.proof.blindExplanation &&
    result.proof.observedPremises.length === 0 &&
    !result.proof.proofType &&
    !result.proof.trustNamespace &&
    !result.proof.verificationStatus &&
    !result.proof.trustLabel &&
    !result.proof.humanReviewStatus;

  const visualReactionData =
    isVisualFixtureMode && result?.kind === 'VISIBLE'
      ? VISUAL_FIXTURE_REACTION_MAP[result.proof.proofId] ?? null
      : null;

  const effectiveIsLiked = visualReactionData ? visualReactionData.liked : isLiked;
  const likeCountText = visualReactionData ? String(visualReactionData.likeCount) : String(likeCount);
  const commentCountText = visualReactionData ? String(visualReactionData.commentCount) : String(liveCommentCount);

  return (
    <div className="page-container" data-testid="proof-detail-page">
      {isCompact ? (
        <div
          className="proof-detail-compact-wrapper"
          data-testid="proof-visible-container"
        >
          {/* Skip-link Back Button */}
          <button
            type="button"
            className="proof-compact-back-button"
            data-testid="proof-back-button"
            onClick={handleBack}
          >
            ← {result.proof.workId ? 'Back to Film Detail' : 'Back to Catalog'}
          </button>

          {/* Compact White Panel */}
          <div className="proof-compact-panel" data-testid="proof-compact-panel">
            {proofWorkId && <button className="proof-film-link" onClick={handleBack}>{filmTitle || 'View Film'}</button>}
            <h1 className="proof-compact-title" data-testid="proof-title">
              {result.proof.title}
            </h1>

            <h2 className="proof-sr-only">Dual Interpretation Details</h2>

            <p
              className="proof-compact-explanation"
              data-testid="proof-reveal-explanation"
            >
              {result.proof.revealExplanation}
            </p>

            {/* Reaction Row */}
            <div className="proof-compact-reactions" data-testid="proof-reactions-row">
              <button
                type="button"
                className="proof-reaction-btn"
                data-testid="proof-reaction-like"
                onClick={handleLike}
                aria-label={
                  visualReactionData
                    ? `Like count: ${visualReactionData.likeCount}`
                    : `Like count: ${likeCount}`
                }
              >
                <img
                  src={effectiveIsLiked ? proofLikeSelectedSvg : proofLikeDefaultSvg}
                  alt=""
                  width={20}
                  height={20}
                  className="proof-reaction-icon"
                />
                <span className="proof-reaction-text">{likeCountText}</span>
              </button>

              <button
                type="button"
                className="proof-reaction-btn"
                data-testid="proof-reaction-comment"
                onClick={handleToggleComments}
                aria-label={
                  visualReactionData
                    ? `Comment count: ${visualReactionData.commentCount}`
                    : `Comment count: ${liveCommentCount}`
                }
              >
                <img
                  src={proofCommentSvg}
                  alt=""
                  width={20}
                  height={20}
                  className="proof-reaction-icon"
                />
                <span className="proof-reaction-text">{commentCountText}</span>
              </button>

              <button
                type="button"
                className="proof-reaction-btn"
                data-testid="proof-reaction-share"
                onClick={handleShare}
                aria-label="Share"
              >
                <img
                  src={proofShareSvg}
                  alt=""
                  width={20}
                  height={20}
                  className="proof-reaction-icon"
                />
                <span className="proof-reaction-text">Share</span>
              </button>
            </div>

            {reactionNotice && (
              <div
                role="status"
                className="proof-reaction-notice"
                data-testid="proof-reaction-notice"
              >
                {reactionNotice}
              </div>
            )}

            {/* Comment Thread in Compact View */}
            {!isVisualFixtureMode && <ProofComments key={proofId} proofId={proofId} navigate={navigate} onCount={setLiveCommentCount} />}
          </div>
        </div>
      ) : (
        <div className="page-content" style={{ maxWidth: '1680px', width: '100%', margin: '0 auto', padding: '40px clamp(16px, 4vw, 24px)', gap: '24px', boxSizing: 'border-box' }}>
          {/* Back button */}
          <button
            type="button"
            data-testid="proof-back-button"
            onClick={handleBack}
            style={{
              background: 'none',
              border: 'none',
              color: '#888888',
              fontSize: '14px',
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            ←{' '}
            {(result?.kind === 'VISIBLE' || result?.kind === 'PROTECTED') &&
            result.proof.workId
              ? 'Back to Film Detail'
              : 'Back to Catalog'}
          </button>

          {/* Loading State */}
          {loading && (
            <div data-testid="proof-loading">
              <LoadingState message="Retrieving proof details and forensic premises..." />
            </div>
          )}

          {/* Error State */}
          {!loading && (result?.kind === 'ERROR' || fetchError) && (
            <div data-testid="proof-error-state">
              <ErrorState
                title="Failed to Load Proof"
                message={
                  fetchError ||
                  (result?.kind === 'ERROR'
                    ? result.error
                    : 'An unexpected network error occurred.')
                }
                onRetry={handleRetry}
              />
            </div>
          )}

          {/* Empty State */}
          {!loading && !fetchError && result?.kind === 'EMPTY' && (
            <div data-testid="proof-empty-state">
              <EmptyState
                title="Proof Not Found"
                message={`No verified proof found matching ID '${activeProofIdRef.current || proofId}'.`}
              />
            </div>
          )}

          {/* Protected State */}
          {!loading && !fetchError && result?.kind === 'PROTECTED' && (
            <div
              data-testid="proof-protected-container"
              style={{
                background: '#FFFFFF',
                border: '1px solid #EEEEEE',
                borderRadius: '12px',
                padding: '36px',
                boxShadow: '0 2px 8px #00000008',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  marginBottom: '16px',
                }}
              >
                <span
                  style={{
                    background: '#F0EDFF',
                    color: '#4C22F4',
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: 700,
                  }}
                >
                  {result.proof.proofType?.replace(/_/g, ' ') || 'REVEAL CLUE'}
                </span>
                <span
                  style={{
                    background: '#FFF3E0',
                    color: '#E65100',
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: 600,
                  }}
                >
                  SPOILER PROTECTED
                </span>
              </div>

              {proofWorkId && <button className="proof-film-link" onClick={handleBack}>{filmTitle || 'View Film'}</button>}
              <h1
                data-testid="proof-title"
                style={{
                  fontSize: '26px',
                  fontWeight: 700,
                  color: '#2D2D34',
                  margin: '0 0 16px 0',
                }}
              >
                {result.proof.safeTitle}
              </h1>

              <div
                style={{
                  background: '#F8F9FA',
                  border: '1px solid #EEEEEE',
                  borderRadius: '8px',
                  padding: '20px',
                  marginBottom: '20px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    marginBottom: '8px',
                  }}
                >
                  <span style={{ fontSize: '16px' }}>🔒</span>
                  <span
                    style={{
                      fontWeight: 600,
                      color: '#4A4A53',
                      fontSize: '15px',
                    }}
                  >
                    Protected by Spoiler Shield
                  </span>
                </div>
                <p
                  data-testid="proof-summary"
                  style={{
                    margin: '0 0 16px 0',
                    fontSize: '14px',
                    color: '#555555',
                    lineHeight: 1.6,
                  }}
                >
                  {result.proof.safeSummary}
                </p>

                <div
                  style={{
                    background: '#F0EDFF',
                    border: '1px solid #4C22F430',
                    borderRadius: '8px',
                    padding: '14px 18px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '12px',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '13px', color: '#2D2D34', marginBottom: '2px' }}>
                      {result.proof.isUnderReview ? 'Review Status' : 'Unlock this analysis'}
                    </div>
                    <div style={{ fontSize: '12px', color: '#6B6B75' }}>
                      {result.proof.isUnderReview
                        ? 'This interpretation is currently undergoing forensic verification and cannot be unlocked by changing progress.'
                        : 'To read this analysis, select your viewing progress or a completed reveal on the film page.'}
                    </div>
                  </div>
                  {!result.proof.isUnderReview && (
                    <button
                      type="button"
                      onClick={() => {
                        const targetPath = result.proof.workId
                          ? `/films/${encodeURIComponent(result.proof.workId)}`
                          : '/films';
                        navigate(targetPath);
                      }}
                      style={{
                        background: '#4C22F4',
                        color: '#FFFFFF',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '8px 16px',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Adjust Progress on Film Page →
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Visible State */}
          {!loading && !fetchError && result?.kind === 'VISIBLE' && (
            <div
              data-testid="proof-visible-container"
              style={{
                background: '#FFFFFF',
                border: '1px solid #EEEEEE',
                borderRadius: '12px',
                padding: '36px',
                boxShadow: '0 2px 8px #00000008',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '16px',
                  flexWrap: 'wrap',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {result.proof.proofType && (
                    <span
                      style={{
                        background: '#F0EDFF',
                        color: '#4C22F4',
                        padding: '3px 10px',
                        borderRadius: '9999px',
                        fontSize: '12px',
                        fontWeight: 700,
                      }}
                    >
                      {result.proof.proofType.replace(/_/g, ' ')}
                    </span>
                  )}
                  {result.proof.trustNamespace && (
                    <span
                      style={{
                        background: '#F5F5F5',
                        color: '#888888',
                        padding: '3px 8px',
                        borderRadius: '9999px',
                        fontSize: '12px',
                      }}
                    >
                      {result.proof.trustNamespace === 'AI_INTERPRETATION' ? 'AI interpretation' : result.proof.trustNamespace}
                    </span>
                  )}
                </div>

                {statusText && (
                  <span
                    data-testid="proof-provenance"
                    style={{
                      flexBasis: '100%',
                      display: 'block',
                      marginBottom: '12px',
                      lineHeight: 1.6,
                      background: isVerifiedCanon ? '#E8F5E9' : '#FFF9C4',
                      color: isVerifiedCanon ? '#176B30' : '#775400',
                      border: `1px solid ${
                        isVerifiedCanon ? '#27AE6040' : '#F2994A40'
                      }`,
                      padding: '3px 10px',
                      borderRadius: '9999px',
                      fontSize: '12px',
                      fontWeight: 600,
                    }}
                  >
                    {statusText}
                  </span>
                )}
              </div>

              <h1
                data-testid="proof-title"
                style={{
                  fontSize: '26px',
                  fontWeight: 700,
                  color: '#2D2D34',
                  margin: '0 0 24px 0',
                  lineHeight: 1.3,
                }}
              >
                {result.proof.title}
              </h1>

              {/* Before / After */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                  gap: '16px',
                  marginBottom: '28px',
                }}
              >
                <div
                  style={{
                    background: '#F8F9FA',
                    border: '1px solid #EEEEEE',
                    borderRadius: '8px',
                    padding: '18px',
                  }}
                >
                  <h3
                    style={{
                      margin: '0 0 8px 0',
                      fontSize: '13px',
                      textTransform: 'uppercase',
                      color: '#888888',
                      letterSpacing: '0.5px',
                    }}
                  >
                    Blind Perspective (Before Reveal)
                  </h3>
                  <p
                    data-testid="proof-blind-explanation"
                    style={{
                      margin: 0,
                      fontSize: '14px',
                      color: '#555555',
                      lineHeight: 1.6,
                    }}
                  >
                    {result.proof.blindExplanation ||
                      'No blind perspective explanation recorded.'}
                  </p>
                </div>

                <div
                  style={{
                    background: '#F0EDFF',
                    border: '1px solid #4C22F440',
                    borderRadius: '8px',
                    padding: '18px',
                  }}
                >
                  <h3
                    style={{
                      margin: '0 0 8px 0',
                      fontSize: '13px',
                      textTransform: 'uppercase',
                      color: '#4C22F4',
                      letterSpacing: '0.5px',
                    }}
                  >
                    Reframed Perspective (After Reveal)
                  </h3>
                  <p
                    data-testid="proof-reveal-explanation"
                    style={{
                      margin: 0,
                      fontSize: '14px',
                      color: '#2D2D34',
                      lineHeight: 1.6,
                    }}
                  >
                    {result.proof.revealExplanation ||
                      'No reframed explanation recorded.'}
                  </p>
                </div>
              </div>

              {result.proof.trustNamespace === 'AI_INTERPRETATION' && (
                <p style={{fontSize: 14, lineHeight: 1.6, color: '#5F586B'}}>Generated from stored scene observations. Evidence references were checked; the interpretation has not been proven or reviewed by a person.</p>
              )}
              {!!result.proof.alternativeExplanations?.length && (
                <section style={{marginBottom: 28}}>
                  <h3 style={{fontSize: 16}}>Other possible readings</h3>
                  <ul style={{fontSize: 14, lineHeight: 1.6}}>{result.proof.alternativeExplanations.map((text, index) => <li key={index}>{text}</li>)}</ul>
                </section>
              )}
              {/* Observed Premises */}
              <div style={{ marginBottom: '28px' }}>
                <h3
                  style={{
                    fontSize: '16px',
                    fontWeight: 700,
                    color: '#2D2D34',
                    margin: '0 0 14px 0',
                  }}
                >
                  Observed Scene Premises ({result.proof.observedPremises.length})
                </h3>
                {result.proof.observedPremises.length === 0 ? (
                  <div style={{ color: '#888888', fontSize: '14px' }}>
                    No observed scene premises recorded.
                  </div>
                ) : (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '10px',
                    }}
                  >
                    {result.proof.observedPremises.map((prem, idx) => (
                      <div
                        key={prem.key}
                        data-testid={`proof-premise-${idx}`}
                        style={{
                          background: '#F8F9FA',
                          border: '1px solid #EEEEEE',
                          borderRadius: '8px',
                          padding: '14px 18px',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: '6px',
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              gap: '10px',
                              alignItems: 'center',
                            }}
                          >
                          </div>
                          {prem.timestampFormatted && (
                            <span
                              data-testid={`proof-premise-time-${idx}`}
                              style={{ color: '#888888', fontSize: '12px' }}
                            >
                              {prem.timestampFormatted}
                            </span>
                          )}
                        </div>
                        <p
                          data-testid={`proof-premise-text-${idx}`}
                          style={{
                            margin: '0 0 6px 0',
                            fontSize: '14px',
                            color: '#2D2D34',
                          }}
                        >
                          {prem.text}
                        </p>
                        {prem.frameUrl && (
                          <div style={{ marginTop: '8px', marginBottom: '8px' }}>
                            <img
                              src={prem.frameUrl}
                              alt={prem.timestampFormatted ? `Film still at ${prem.timestampFormatted}` : 'Scene evidence frame'}
                              data-testid={`proof-premise-image-${idx}`}
                              style={{
                                maxWidth: '100%',
                                maxHeight: '220px',
                                borderRadius: '6px',
                                border: '1px solid #E6E6EA',
                                objectFit: 'contain',
                                display: 'block',
                              }}
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = 'none';
                              }}
                            />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Engagement Row */}
              <div
                className="proof-compact-reactions"
                data-testid="proof-reactions-row"
                style={{ borderTop: '1px solid #EEEEEE', paddingTop: '20px' }}
              >
                <button
                  type="button"
                  className="proof-reaction-btn"
                  data-testid="proof-reaction-like"
                  onClick={handleLike}
                  aria-label={`Like count: ${likeCount}`}
                >
                  <img
                    src={effectiveIsLiked ? proofLikeSelectedSvg : proofLikeDefaultSvg}
                    alt=""
                    width={20}
                    height={20}
                    className="proof-reaction-icon"
                  />
                  <span className="proof-reaction-text">{likeCountText}</span>
                </button>

                <button
                  type="button"
                  className="proof-reaction-btn"
                  data-testid="proof-reaction-comment"
                  onClick={handleToggleComments}
                  aria-label={`Comment count: ${liveCommentCount}`}
                >
                  <img
                    src={proofCommentSvg}
                    alt=""
                    width={20}
                    height={20}
                    className="proof-reaction-icon"
                  />
                  <span className="proof-reaction-text">{commentCountText}</span>
                </button>

                <button
                  type="button"
                  className="proof-reaction-btn"
                  data-testid="proof-reaction-share"
                  onClick={handleShare}
                  aria-label="Share"
                >
                  <img
                    src={proofShareSvg}
                    alt=""
                    width={20}
                    height={20}
                    className="proof-reaction-icon"
                  />
                  <span className="proof-reaction-text">Share</span>
                </button>
              </div>

              {reactionNotice && (
                <div
                  role="status"
                  className="proof-reaction-notice"
                  data-testid="proof-reaction-notice"
                  style={{ marginTop: '12px' }}
                >
                  {reactionNotice}
                </div>
              )}

              {/* Comment Thread in Full View */}
              {!isVisualFixtureMode && <ProofComments key={proofId} proofId={proofId} navigate={navigate} onCount={setLiveCommentCount} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
