import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../services/apiClient';
import { useAuth } from '../context/AuthContext';
import { WriteAccessGate } from '../components/WriteAccessGate';
import { ErrorState, LoadingState } from '../components/FeedbackStates';
import { DeleteConfirmation } from '../components/DeleteConfirmation';
import { CommentSpoiler } from '../components/CommentSpoiler';

interface PostDetailPageProps {
  postId?: string;
  navigate?: (path: string) => void;
}

export const PostDetailPage: React.FC<PostDetailPageProps> = ({ postId, navigate }) => {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const canWrite = () => {
    if (authLoading) return false;
    if (!isAuthenticated) { navigate?.('/login'); return false; }
    return true;
  };
  const [post, setPost] = useState<any>(null);
  const [deletingComment, setDeletingComment] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [likes, setLikes] = useState(0);

  // Counterclaim state
  const [showCounterclaimForm, setShowCounterclaimForm] = useState<boolean>(false);
  const [counterclaimText, setCounterclaimText] = useState<string>('');
  const [isSubmittingCc, setIsSubmittingCc] = useState<boolean>(false);
  const [ccError, setCcError] = useState<string | null>(null);
  const [targetClaimId, setTargetClaimId] = useState('');
  const [challengedPremise, setChallengedPremise] = useState('');
  const [sceneId, setSceneId] = useState('');
  const [sceneOptions, setSceneOptions] = useState<Array<{scene_id: string; start_ms: number}>>([]);
  const [commentText, setCommentText] = useState('');
  const [commentBusy, setCommentBusy] = useState(false);
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editingCommentText, setEditingCommentText] = useState<string>('');
  const [editingCommentVersion, setEditingCommentVersion] = useState<number>(1);
  const [shareToast, setShareToast] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const fetchPost = async () => {
    const requestId = ++requestSequence.current;
    if (!postId) {
      setIsLoading(false);
      return;
    }
    try {
      setIsLoading(true);
      setErrorMsg(null);
      const res = await apiClient.community.getPost(postId);
      if (requestId !== requestSequence.current) return;
      if (res && res.data) {
        setPost(res.data);
        setLikes(res.data.likes_count || 0);
        if (isAuthenticated) {
          apiClient.catalog.getSceneIndex(res.data.work_id).then(r => setSceneOptions(r.data)).catch(() => setSceneOptions([]));
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load post.');
    } finally {
      if (requestId === requestSequence.current) setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPost();
  }, [postId, isAuthenticated]);

  const handleLike = async () => {
    if (!postId) return;
    try {
      await apiClient.community.reactToPost(postId, 'LIKE');
      await fetchPost();
    } catch (error: any) { setCcError(error.message); }
  };

  const handleUnlockPost = async () => {
    if (!postId || !post) return;
    try {
      await apiClient.community.unlockContent('POST', postId, post.version_no || 1);
      await fetchPost();
    } catch (err: any) {
      setCcError(err.message || 'Failed to unlock post');
    }
  };

  const handleSharePost = () => {
    if (!postId) return;
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const shareUrl = `${origin}/posts/${postId}`;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(shareUrl).then(() => {
        setShareToast(`Post link copied to clipboard: ${shareUrl}`);
        setTimeout(() => setShareToast(null), 3500);
      }).catch(() => {
        setShareToast(`Post link: ${shareUrl}`);
        setTimeout(() => setShareToast(null), 3500);
      });
    } else {
      setShareToast(`Post link: ${shareUrl}`);
      setTimeout(() => setShareToast(null), 3500);
    }
  };

  const submitComment = async () => {
    if (!canWrite()) return;
    if (!postId || !commentText.trim()) return;
    setCommentBusy(true); setCcError(null);
    try {
      await apiClient.community.createComment(postId, commentText.trim());
      setCommentText(''); await fetchPost();
    } catch (error: any) { setCcError(error.message); }
    finally { setCommentBusy(false); }
  };

  const handleStartEditComment = (c: any) => {
    if (!canWrite() || !c.can_edit) return;
    setEditingCommentId(c.comment_id || c.id);
    setEditingCommentText(c.body_markdown || '');
    setEditingCommentVersion(c.version_no || 1);
  };

  const handleSaveEditComment = async () => {
    if (!canWrite()) return;
    if (!postId || !editingCommentId || !editingCommentText.trim()) return;
    try {
      await apiClient.community.updateComment(postId, editingCommentId, {
        body_markdown: editingCommentText.trim(),
        expected_version: editingCommentVersion,
      });
      setEditingCommentId(null);
      setEditingCommentText('');
      await fetchPost();
    } catch (err: any) {
      setCcError(err.message || 'Failed to update comment');
    }
  };

  const handleCancelEditComment = () => {
    setEditingCommentId(null);
    setEditingCommentText('');
  };

  const handleDeleteComment = async (commentId: string) => {
    if (!canWrite()) return;
    if (!postId) return;
    await apiClient.community.deleteComment(postId, commentId);
    await fetchPost();
  };

  const handleUnlockComment = async (commentId: string, versionNo: number = 1) => {
    try {
      await apiClient.community.unlockContent('COMMENT', commentId, versionNo);
      await fetchPost();
    } catch (err: any) {
      setCcError(err.message || 'Failed to unlock comment');
    }
  };

  const handleSubmitCounterclaim = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!canWrite()) return;
    if (!postId || !counterclaimText.trim() || !targetClaimId || !challengedPremise.trim() || !sceneId) return;

    setIsSubmittingCc(true);
    setCcError(null);

    try {
      await apiClient.community.createCounterclaim(postId, {
        target_claim_id: targetClaimId,
        challenged_premise: challengedPremise.trim(),
        alternative_explanation: counterclaimText.trim(),
        evidence_links: [
          {
            evidence_type: 'scene',
            evidence_id: sceneId
          }
        ]
      });

      setCounterclaimText('');
      setChallengedPremise(''); setTargetClaimId(''); setSceneId('');
      setShowCounterclaimForm(false);
      // Refresh post detail to show new counterclaim
      await fetchPost();
    } catch (err: any) {
      setCcError(err.message || 'Failed to submit counterclaim.');
    } finally {
      setIsSubmittingCc(false);
    }
  };

  if (isLoading) return <LoadingState message="Loading discussion..." />;
  if (errorMsg || !post) return <ErrorState message={errorMsg || 'Discussion not found.'} />;
  const isPostMasked = Boolean(post.is_locked || post.visibility === 'LOCKED' || post.visibility === 'MASKED' || post.is_spoiler_masked);
  const titleText = post.title;
  const authorName = post?.author_name || 'Audience Author';
  const publishedDate = post?.published_at
    ? post.published_at.slice(0, 10)
    : '';
  const bodyText = post?.body_markdown || post?.safe_preview?.summary || 'Complete watching the film to reveal full discussion.';
  const counterclaimsList = post?.counterclaims || [];

  return (
    <div className="live-post-detail" data-layer="Community - Detail Page" style={{ width: '100%', minHeight: '100vh', position: 'relative', background: 'var(--Gray-0, white)', flexDirection: 'column', display: 'flex' }}>
      {deletingComment && <DeleteConfirmation kind="comment" detail="Replies will be kept." onCancel={() => setDeletingComment(null)} onDelete={() => handleDeleteComment(deletingComment)} />}
      <div className="journey-actions" style={{padding: '16px 24px'}}><button onClick={() => navigate?.('/films')}>Back to Films</button></div>
      <div data-layer="Frame 2147227211" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
        <div data-layer="Frame 2147227296" style={{ alignSelf: 'stretch', paddingBottom: 80, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 32, display: 'flex' }}>

          {/* Post Content Container (1:1 Figma Frame 2147227195) */}
          <div data-layer="Frame 2147227195" style={{ alignSelf: 'stretch', boxSizing: 'border-box', paddingLeft: 120, paddingRight: 120, paddingTop: 37, paddingBottom: 40, outline: '1px var(--Gray-100, #F2F2F5) solid', outlineOffset: '-1px', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 28, display: 'flex' }}>
            <div data-layer="Frame 2147227288" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 28, display: 'flex' }}>
              <div data-layer="Frame 2147227290" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
                <div data-layer="Frame 2147227289" style={{ alignSelf: 'stretch', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'inline-flex' }}>
                  <div
                    data-testid="post-detail-title"
                    data-layer="Title"
                    style={{ flex: '1 1 0', color: 'var(--Gray-800, #2D2D34)', fontSize: 28, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '39.20px', wordWrap: 'break-word' }}
                  >
                    {titleText}
                  </div>
                  <div data-layer="2026.06.12" style={{ color: 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>
                    {publishedDate}
                  </div>
                </div>
                <div data-layer="Author" style={{ color: 'var(--Gray-600, #6B6B75)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>
                  {authorName}
                </div>
              </div>

              {/* Body Text or Spoiler Warning */}
              {isPostMasked ? (
                <div style={{ alignSelf: 'stretch', padding: 20, background: '#FFFBEB', borderRadius: 12, border: '1px solid #FDE68A', display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: '#92400E' }}>
                    ⚠️ Spoiler Protected Discussion
                  </div>
                  <div style={{ fontSize: 14, color: '#B45309' }}>
                    {post.safe_preview?.summary || 'This discussion contains potential spoilers or unverified narrative clues beyond your current watch progress.'}
                  </div>
                  <div style={{ display: 'flex', gap: 12, marginTop: 4, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={handleUnlockPost}
                      style={{
                        padding: '8px 18px',
                        background: '#F59E0B',
                        color: '#FFFFFF',
                        border: 'none',
                        borderRadius: 8,
                        fontSize: 14,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Confirm Warning & Reveal Post
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate?.(`/films/${post.work_id}`)}
                      style={{
                        padding: '8px 16px',
                        background: '#FFFFFF',
                        color: '#78350F',
                        border: '1px solid #FCD34D',
                        borderRadius: 8,
                        fontSize: 14,
                        cursor: 'pointer',
                      }}
                    >
                      View Watch Progress
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    alignSelf: 'stretch',
                    minHeight: 96,
                    boxSizing: 'border-box',
                    color: 'var(--Gray-600, #6B6B75)',
                    fontSize: 16,
                    fontFamily: 'Pretendard',
                    fontWeight: '400',
                    lineHeight: '24px',
                    wordWrap: 'break-word',
                    whiteSpace: 'pre-wrap'
                  }}
                >
                  {bodyText}
                </div>
              )}

              {post.validation_summary && <div data-testid="published-validation-summary" role="status">
                Analysis: {post.validation_summary.status} · {post.validation_summary.validation_verdict} · {post.validation_summary.validation_mode}
                <p>Engine evidence cross-check results; not canonical verification.</p>
              </div>}
              {(post.claims || []).map((claim: any) => <div key={claim.claim_id} style={{padding: 16, background: '#F8F8FA', borderRadius: 8}}><strong>Author's Claim</strong><p>{claim.text}</p></div>)}
            </div>

            {/* Interaction Bar (1:1 Figma Frame 2147227304) */}
            <div data-layer="Frame 2147227304" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 12, display: 'inline-flex' }}>
              <button type="button" aria-label={`Toggle like, current ${likes}`} onClick={handleLike} data-layer="LikeButton" data-state="Default" style={{ border: 0, background: 'transparent', padding: 6, borderRadius: 8, justifyContent: 'center', alignItems: 'center', gap: 6, display: 'flex', cursor: 'pointer' }}>
                <div data-layer="Icon" style={{ width: 20, height: 20, position: 'relative' }}>
                  <svg width="100%" height="100%" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M10.293 17.4268C10.1097 17.5241 9.89032 17.5241 9.70703 17.4268L10 16.875L10.293 17.4268ZM16.875 6.875C16.875 5.17291 15.4302 3.75 13.5938 3.75C12.2253 3.75 11.0661 4.54535 10.5713 5.65674C10.4709 5.88228 10.2469 6.02783 10 6.02783C9.75312 6.02783 9.52909 5.88228 9.42871 5.65674C8.93392 4.54535 7.77467 3.75 6.40625 3.75C4.56977 3.75 3.125 5.17291 3.125 6.875C3.125 9.62122 4.84375 11.9659 6.67643 13.6743C7.58245 14.5189 8.49097 15.184 9.17399 15.638C9.5147 15.8645 9.79788 16.0376 9.9943 16.1532C9.99607 16.1542 9.99825 16.1554 10 16.1564C10.0017 16.1554 10.0039 16.1542 10.0057 16.1532C10.2021 16.0376 10.4853 15.8645 10.826 15.638C11.509 15.184 12.4175 14.5189 13.3236 13.6743C15.1562 11.9659 16.875 9.62122 16.875 6.875ZM18.125 6.875C18.125 10.1457 16.0937 12.8009 14.1764 14.5882C13.2076 15.4914 12.2409 16.1981 11.5177 16.6789C11.1556 16.9196 10.8526 17.1049 10.6388 17.2306C10.5322 17.2934 10.4478 17.3419 10.389 17.3747C10.3596 17.3911 10.3359 17.4034 10.3198 17.4121C10.3119 17.4164 10.3056 17.4203 10.3011 17.4227C10.299 17.4238 10.2975 17.4252 10.2962 17.4259L10.2938 17.4268L10 16.875L9.70622 17.4268L9.70378 17.4259C9.70246 17.4252 9.70101 17.4238 9.69889 17.4227C9.6944 17.4203 9.68815 17.4164 9.68018 17.4121C9.6641 17.4034 9.64045 17.3911 9.611 17.3747C9.55217 17.3419 9.46783 17.2934 9.36117 17.2306C9.14745 17.1049 8.84445 16.9196 8.48226 16.6789C7.75909 16.1981 6.7924 15.4914 5.82357 14.5882C3.90634 12.8009 1.875 10.1457 1.875 6.875C1.875 4.43495 3.928 2.5 6.40625 2.5C7.86485 2.5 9.16869 3.16863 10 4.21387C10.8313 3.16863 12.1352 2.5 13.5938 2.5C16.072 2.5 18.125 4.43495 18.125 6.875Z" fill="var(--Gray-400, #AFAFB8)" />
                  </svg>
                </div>
                <div data-layer="Like Count" style={{ color: 'var(--Gray-400, #AFAFB8)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '600', wordWrap: 'break-word' }}>
                  {likes}
                </div>
              </button>
              <button
                type="button"
                aria-label="Share post"
                onClick={handleSharePost}
                style={{
                  border: 'none',
                  background: '#F1F0FF',
                  color: '#4C22F4',
                  padding: '6px 14px',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6
                }}
              >
                Share
              </button>
            </div>
          </div>

          {/* Evidence-Based Counterclaim Section */}
          <div style={{ alignSelf: 'stretch', paddingLeft: 120, paddingRight: 120, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'flex' }}>
            <div style={{ alignSelf: 'stretch', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ color: 'var(--Global-Text-Medium, #475569)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '700' }}>
                Evidence-Based Counterclaims ({counterclaimsList.length})
              </div>
              <button
                type="button"
                data-testid="counterclaim-btn"
                disabled={authLoading || (isAuthenticated && !post?.claims?.length)}
                onClick={() => { if (canWrite()) setShowCounterclaimForm(!showCounterclaimForm); }}
                style={{
                  background: '#4C22F4',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 8,
                  padding: '8px 16px',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                {showCounterclaimForm ? 'Close Form' : 'Submit Counterclaim'}
              </button>
            </div>
            {ccError && <p role="alert" style={{color: '#B42318'}}>{ccError}</p>}

            {/* Counterclaim Input Form */}
            {isAuthenticated && showCounterclaimForm && (
              <div style={{ alignSelf: 'stretch', background: '#F8F9FA', border: '1px solid #E2E8F0', borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#2D2D34' }}>
                  Submit a counterclaim supported by forensic scene evidence
                </div>
                {ccError && (
                  <div style={{ color: '#EB5757', fontSize: 13 }}>{ccError}</div>
                )}
                <textarea
                  data-testid="counterclaim-input"
                  aria-label="Alternative Explanation"
                  value={counterclaimText}
                  onChange={(e) => setCounterclaimText(e.target.value)}
                  placeholder="Enter your counter-argument and supporting scene clues (e.g. Scene 17)..."
                  style={{
                    width: '100%',
                    minHeight: 90,
                    padding: 12,
                    borderRadius: 8,
                    border: '1px solid #CBD5E0',
                    fontSize: 14,
                    fontFamily: 'Pretendard',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
                <label>Challenged Claim
                  <select aria-label="Challenged Claim" value={targetClaimId} onChange={e => setTargetClaimId(e.target.value)}>
                    <option value="">Select a claim</option>
                    {(post.claims || []).map((claim: any) => <option key={claim.claim_id} value={claim.claim_id}>{claim.text}</option>)}
                  </select>
                </label>
                <label>Challenged Premise<input aria-label="Challenged Premise" value={challengedPremise} onChange={e => setChallengedPremise(e.target.value)} /></label>
                <label>Evidence Scene
                  <select aria-label="Evidence Scene" value={sceneId} onChange={e => setSceneId(e.target.value)}>
                    <option value="">Select a scene</option>
                    {sceneOptions.map(scene => <option key={scene.scene_id} value={scene.scene_id}>{scene.scene_id} · {Math.floor(scene.start_ms / 60000)}m</option>)}
                  </select>
                </label>
                {!sceneOptions.length && <p>Evidence scenes can be selected after saving watch progress on film detail.</p>}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button
                    type="button"
                    data-testid="submit-counterclaim-btn"
                    onClick={handleSubmitCounterclaim}
                    disabled={isSubmittingCc || !counterclaimText.trim() || !targetClaimId || !challengedPremise.trim() || !sceneId}
                    style={{
                      background: '#27AE60',
                      color: '#FFFFFF',
                      border: 'none',
                      borderRadius: 8,
                      padding: '8px 20px',
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: isSubmittingCc || !counterclaimText.trim() ? 'not-allowed' : 'pointer'
                    }}
                  >
                    {isSubmittingCc ? 'Submitting...' : 'Submit Counterclaim'}
                  </button>
                </div>
              </div>
            )}

            {/* Counterclaims List */}
            <div data-testid="counterclaims-list" style={{ alignSelf: 'stretch', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {counterclaimsList.length === 0 ? (
                <div style={{ color: '#898992', fontSize: 14, padding: '12px 0' }}>
                  No counterclaims registered yet. Be the first to submit evidence-backed analysis!
                </div>
              ) : (
                counterclaimsList.map((cc: any, idx: number) => (
                  <div
                    key={cc.counterclaim_id || idx}
                    style={{
                      background: '#F8F9FA',
                      border: '1px solid #E2E8F0',
                      borderRadius: 12,
                      padding: 18,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#4C22F4' }}>
                        Counterclaim
                      </span>
                      <span style={{ fontSize: 12, color: '#8C9BB0' }}>
                        Author: {cc.author_name || 'Audience Member'}
                      </span>
                    </div>
                    <div style={{ color: '#2D2D34', fontSize: 15, lineHeight: 1.5 }}>
                      <p>Challenged premise: {cc.challenged_premise}</p>
                      {cc.alternative_explanation}
                    </div>
                    {cc.evidence_links && cc.evidence_links.length > 0 && (
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                        {cc.evidence_links.map((ev: any, evIdx: number) => (
                          <span
                            key={evIdx}
                            style={{
                              background: '#F0EDFF',
                              color: '#4C22F4',
                              fontSize: 11,
                              fontWeight: 600,
                              padding: '2px 8px',
                              borderRadius: 4
                            }}
                          >
                            Evidence: {ev.evidence_id || ev.evidence_type}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          <section style={{width: '100%', padding: '0 120px', boxSizing: 'border-box', marginTop: 24}}>
            <h2 style={{fontSize: 20, color: '#2D2D34', marginBottom: 16}}>Comments</h2>
            {(post.comments || []).map((comment: any) => {
              const cId = comment.comment_id || comment.id;
              const isEditing = editingCommentId === cId;
              const isCommentMasked = Boolean(comment.is_spoiler_masked || comment.is_locked || comment.visibility === 'MASKED');

              if (isAuthenticated && isEditing) {
                return (
                  <div key={cId} style={{ padding: '12px 16px', background: '#F8F8FA', borderRadius: 8, marginBottom: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <input
                      type="text"
                      value={editingCommentText}
                      onChange={(e) => setEditingCommentText(e.target.value)}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #4C22F4', fontSize: 14, fontFamily: 'Pretendard' }}
                    />
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        onClick={handleSaveEditComment}
                        style={{ padding: '6px 14px', background: '#4C22F4', color: '#FFF', border: 'none', borderRadius: 6, fontSize: 13, cursor: 'pointer' }}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={handleCancelEditComment}
                        style={{ padding: '6px 14px', background: '#E5E7EB', color: '#374151', border: 'none', borderRadius: 6, fontSize: 13, cursor: 'pointer' }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                );
              }

              if (isCommentMasked) {
                return (
                  <CommentSpoiler key={cId} canReveal={Boolean(comment.can_reveal)} inspectionStatus={comment.inspection_status} onReveal={() => void handleUnlockComment(cId, comment.version_no || 1)} />
                );
              }

              return (
                <div key={cId} style={{ padding: '12px 16px', background: '#F8F8FA', borderRadius: 8, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 14, color: '#2D2D34' }}>
                    {comment.body_markdown}
                  </div>
                  {isAuthenticated && comment.can_edit && <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <button
                      type="button"
                      onClick={() => handleStartEditComment(comment)}
                      style={{ border: 'none', background: 'transparent', color: '#4C22F4', fontSize: 13, cursor: 'pointer' }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeletingComment(cId)}
                      style={{ border: 'none', background: 'transparent', color: '#DC2626', fontSize: 13, cursor: 'pointer' }}
                    >
                      Delete
                    </button>
                  </div>}
                </div>
              );
            })}
            <WriteAccessGate navigate={navigate}>
            <form onSubmit={e => { e.preventDefault(); submitComment(); }} style={{marginTop: 16}}>
              <textarea
                aria-label="Comments"
                value={commentText}
                onChange={e => setCommentText(e.target.value)}
                placeholder="Share your thoughts on this film..."
                rows={3}
                style={{width: '100%', boxSizing: 'border-box', padding: 12, border: '1px solid #CBD5E0', borderRadius: 8, fontFamily: 'Pretendard'}}
              />
              <button
                type="submit"
                disabled={commentBusy || !commentText.trim()}
                style={{marginTop: 8, padding: '10px 18px', background: '#4C22F4', color: 'white', border: 0, borderRadius: 8, cursor: 'pointer', fontWeight: 600}}
              >
                {commentBusy ? 'Posting...' : 'Post Comment'}
              </button>
            </form>
            </WriteAccessGate>
          </section>

          {/* Share Toast Notification */}
          {shareToast && (
            <div style={{ position: 'fixed', bottom: 24, right: 24, background: '#1E293B', color: '#FFFFFF', padding: '12px 20px', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.15)', zIndex: 9999, fontSize: 14, fontFamily: 'Pretendard' }}>
              {shareToast}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};
