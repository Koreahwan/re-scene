import React, { useEffect, useRef, useState } from 'react';
import { apiClient, communityApi } from '../services/apiClient';
import { useAuth } from '../context/AuthContext';
import { AppModal } from './AppModal';
import { DeleteConfirmation } from './DeleteConfirmation';
import { RatingStars } from './RatingStars';
import { ProofComments } from './ProofComments';
import { CommentSpoiler } from './CommentSpoiler';
import { loginDestination } from '../utils/navigation';
import filledStar from '../assets/figma/rating-star-filled.svg';
import emptyStar from '../assets/figma/rating-star-empty.svg';

export function TopBoxReviews({ pageId, title, navigate, openRequest }: {
  pageId: number; title: string; navigate: (path: string) => void; openRequest: number;
}) {
  const { user, isAuthenticated, loading: authLoading } = useAuth();
  const [target, setTarget] = useState<{ work_id: string; edition_id: string; title: string } | null>(null);
  const [posts, setPosts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [open, setOpen] = useState(false), [pending, setPending] = useState(false);
  const [text, setText] = useState(''), [rating, setRating] = useState(0), [spoilers, setSpoilers] = useState(false);
  const [editing, setEditing] = useState<any>(null), [deleting, setDeleting] = useState<any>(null);
  const [reveal, setReveal] = useState<any>(null), [expanded, setExpanded] = useState<string | null>(null);
  const busy = useRef(false), requestKey = useRef(crypto.randomUUID());
  const viewer = useRef(user?.id); viewer.current = user?.id;
  useEffect(() => { setOpen(false); setText(''); setEditing(null); setDeleting(null); setReveal(null); }, [user?.id]);
  const own = posts.find(post => post.author_id === user?.id);
  useEffect(() => {
    if (authLoading) return;
    let active = true; setLoading(true); setError(''); setPosts([]); setTarget(null);
    (async () => {
      const identity = (await apiClient.community.getTopBoxReviewTarget(pageId)).data;
      const rows = (await communityApi.getPosts(identity.work_id, undefined, 'latest')).data.filter((post: any) => post.rating != null);
      if (identity.own_post_id && !rows.some((post: any) => post.post_id === identity.own_post_id)) rows.unshift((await communityApi.getPost(identity.own_post_id)).data);
      if (active) { setTarget(identity); setPosts(rows); }
    })().catch(failure => { if (active) setError(failure instanceof Error ? failure.message : 'Unable to load reviews.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [pageId, user?.id, authLoading, revision]);
  const start = async () => {
    if (loading || authLoading || busy.current || !target) return;
    if (!isAuthenticated) { navigate(loginDestination(`/box-office/film?title=${encodeURIComponent(title)}&pageId=${pageId}`)); return; }
    setError(''); requestKey.current = crypto.randomUUID();
    const requestedViewer = viewer.current;
    if (own) {
      // The owner's body is available through the authenticated detail route.
      try {
        const current = (await communityApi.getPost(own.post_id)).data;
        if (viewer.current !== requestedViewer) return;
        if (current.is_spoiler_masked || current.is_locked) { setReveal(own); return; }
        setEditing(current); setText(current.body_markdown); setRating(current.rating || 0); setSpoilers(Boolean(current.contains_spoilers));
      } catch { setError('Unable to open your review. Try again.'); return; }
    } else { setEditing(null); setText(''); setRating(0); setSpoilers(false); }
    setOpen(true);
  };
  const consumedRequest = useRef(0);
  useEffect(() => {
    if (openRequest > consumedRequest.current && !loading && !authLoading && target) { consumedRequest.current = openRequest; void start(); }
  }, [openRequest, loading, authLoading, target]);
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); if (!target || busy.current || !text.trim() || !rating) return;
    busy.current = true; setPending(true); setError('');
    try {
      if (editing) await communityApi.updatePost(editing.post_id, { expected_version: editing.version_no, body_markdown: text, rating, contains_spoilers: spoilers });
      else await communityApi.createPost({ ...target, title: `Review of ${target.title}`, content_type: 'REVIEW', body_markdown: text,
        rating, contains_spoilers: spoilers, idempotency_key: requestKey.current });
      setOpen(false); setRevision(value => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save your review.'); }
    finally { busy.current = false; setPending(false); }
  };
  const unlockReview = async (post: any) => {
    if (busy.current) return;
    busy.current = true; setPending(true); setError('');
    try {
      await communityApi.unlockContent('POST', post.post_id, post.version_no || 1);
      setReveal(null); setRevision(value => value + 1);
    } catch { setError('Unable to reveal this review. Try again.'); }
    finally { busy.current = false; setPending(false); }
  };
  return <section className="top-box-reviews" aria-label="Reviews">
    <header><h2>Reviews</h2><button disabled={loading || authLoading || !target} onClick={() => void start()}>{own ? 'Edit My Review' : 'Write a Review'}</button></header>
    {loading && <p role="status">Loading reviews…</p>}
    {!open && error && <p role="alert">{error} <button onClick={() => setRevision(value => value + 1)}>Try again</button></p>}
    {!loading && !error && !posts.length && <p>No reviews yet. Be the first to review this release.</p>}
    {posts.map(post => <article className="top-box-review" key={post.post_id}>
      <header><strong>{post.author_name || 'Viewer'}</strong><RatingStars rating={post.rating} /></header>
      {post.is_spoiler_masked || post.is_locked ? <CommentSpoiler key={`${post.post_id}:${post.version_no || 1}`}
        contentKind="review" canReveal pending={pending} inspectionStatus={post.inspection_status}
        onReveal={() => void unlockReview(post)} /> : <p className="comment-body">{post.body_markdown}</p>}
      {post.author_id === user?.id && <div><button onClick={() => void start()}>Edit</button><button onClick={() => setDeleting(post)}>Delete</button></div>}
      <button onClick={() => setExpanded(value => value === post.post_id ? null : post.post_id)} aria-expanded={expanded === post.post_id}>{post.comments_count ?? 0} {post.comments_count === 1 ? 'Comment' : 'Comments'}</button>
      {expanded === post.post_id && <ProofComments key={post.post_id} proofId={post.post_id} postId={post.post_id} navigate={navigate} onCount={count => setPosts(rows => rows.map(row => row.post_id === post.post_id ? { ...row, comments_count: count } : row))} />}
    </article>)}
    <AppModal isOpen={open} title={editing ? 'Edit My Review' : 'Write a Review'} onClose={() => { if (!busy.current) setOpen(false); }}>
      <form onSubmit={save} className="comment-composer">
        <span id="top-box-rating-label">Your rating</span>
        <div role="group" aria-labelledby="top-box-rating-label" style={{ display: 'flex', gap: 8 }}>{[1, 2, 3, 4, 5].map(value => <button type="button" key={value} disabled={pending}
          aria-label={`${value} ${value === 1 ? 'star' : 'stars'}`} aria-pressed={rating === value}
          style={{ border: 0, padding: 4, background: 'transparent', borderRadius: 4 }}
          onClick={() => { setRating(value); requestKey.current = crypto.randomUUID(); }}>
          <img src={value <= rating ? filledStar : emptyStar} alt="" width={32} height={32} />
        </button>)}</div>
        <label htmlFor="top-box-review-body">Your review</label><textarea id="top-box-review-body" disabled={pending} maxLength={10000} required value={text} onChange={event => { setText(event.target.value); requestKey.current = crypto.randomUUID(); }} />
        <label className="comment-spoiler-check"><input className="spoiler-checkbox" type="checkbox" checked={spoilers} disabled={pending} onChange={event => { setSpoilers(event.target.checked); requestKey.current = crypto.randomUUID(); }} />Contains spoilers</label>
        {error && <p role="alert">{error}</p>}
        <div className="comment-submit"><button type="button" disabled={pending} onClick={() => setOpen(false)}>Cancel</button><button type="submit" disabled={pending || !rating || !text.trim()}>{pending ? 'Saving…' : 'Save Review'}</button></div>
      </form>
    </AppModal>
    {deleting && <DeleteConfirmation kind="review" onCancel={() => setDeleting(null)} onDelete={async () => { await communityApi.deletePost(deleting.post_id); setRevision(value => value + 1); }} />}
    <AppModal isOpen={Boolean(reveal)} title="Reveal spoiler content?" size="sm" onClose={() => { if (!busy.current) setReveal(null); }}>
      {reveal && <CommentSpoiler key={`${reveal.post_id}:${reveal.version_no || 1}`} contentKind="review"
        canReveal pending={pending} inspectionStatus={reveal.inspection_status} onReveal={() => void unlockReview(reveal)} />}
      {error && <p role="alert">{error}</p>}
    </AppModal>
  </section>;
}
