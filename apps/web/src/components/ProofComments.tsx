import React, { useEffect, useRef, useState } from 'react';
import { apiClient, communityApi } from '../services/apiClient';
import { useAuth } from '../context/AuthContext';
import { loginDestination } from '../utils/navigation';
import { useUnsavedChanges } from '../utils/useUnsavedChanges';
import './ProofComments.css';
import { DeleteConfirmation } from './DeleteConfirmation';
import { CommentSpoiler } from './CommentSpoiler';

interface Comment {
  comment_id: string; post_id: string; parent_comment_id: string | null;
  author_id: string | null; author_name: string; body_markdown: string;
  created_at: string; version_no: number; status: string;
  contains_spoilers: boolean; is_spoiler_masked: boolean; is_locked?: boolean; visibility?: string;
  inspection_status?: string; can_reveal?: boolean;
}
interface Draft { text: string; spoilers: boolean; parent: string | null; editing: Comment | null; key: string }
const emptyDraft = (): Draft => ({ text: '', spoilers: false, parent: null, editing: null, key: crypto.randomUUID() });

export function ProofComments({ proofId, postId, navigate, onCount }: { proofId: string; postId?: string; navigate: (path: string) => void; onCount: (count: number) => void }) {
  const { user, isAuthenticated, loading: authLoading } = useAuth();
  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [sort, setSort] = useState('oldest');
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [revision, setRevision] = useState(0);
  const [deleting, setDeleting] = useState<Comment | null>(null);
  const busy = useRef(false);
  const alive = useRef(true);
  const countCallback = useRef(onCount); countCallback.current = onCount;
  const composer = useRef<HTMLTextAreaElement>(null);
  const dirty = draft.editing ? draft.text !== draft.editing.body_markdown || draft.spoilers !== draft.editing.contains_spoilers : Boolean(draft.text || draft.spoilers);
  const storageKey = `rescene:comment-draft:${proofId}`;
  useUnsavedChanges(dirty, () => {
    try { sessionStorage.setItem(storageKey, JSON.stringify({ draft, owner: user?.id || null, savedAt: Date.now() })); } catch { /* Storage may be unavailable. */ }
  });
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (authLoading) return;
    try {
      const raw = sessionStorage.getItem(storageKey); if (!raw) return;
      sessionStorage.removeItem(storageKey);
      const saved = JSON.parse(raw);
      if (Date.now() - saved.savedAt < 3600000 && (!saved.owner || saved.owner === user?.id) && typeof saved.draft?.text === 'string') setDraft(saved.draft);
    } catch { /* Invalid or unavailable local storage is ignored. */ }
  }, [authLoading, user?.id, storageKey]);
  useEffect(() => {
    let active = true; setLoading(true); setLoadError('');
    const request = postId ? communityApi.listComments(postId) : apiClient.proof.getProofComments(encodeURIComponent(proofId));
    request.then(result => {
      if (active) { setComments(result.data); countCallback.current(result.data.filter(item => item.status !== 'DELETED').length); }
    }).catch(() => { if (active) setLoadError('Unable to load comments.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [proofId, postId, user?.id, revision]);
  useEffect(() => {
    if (!comments.some(comment => comment.inspection_status === 'PENDING' || comment.inspection_status === 'UNVERIFIED_CALLS_DISABLED')) return;
    const timer = window.setTimeout(() => { if (!document.hidden) setRevision(value => value + 1); }, 10000);
    return () => window.clearTimeout(timer);
  }, [comments]);
  const updateDraft = (patch: Partial<Draft>) => setDraft(value => ({ ...value, ...patch, key: crypto.randomUUID() }));
  const discard = () => !dirty || window.confirm('Discard your unsaved comment?');
  const start = (comment: Comment, edit: boolean) => {
    if (!isAuthenticated) { navigate(loginDestination()); return; }
    if (busy.current || !discard()) return;
    setDraft({ ...emptyDraft(), text: edit ? comment.body_markdown : comment.parent_comment_id ? `@${comment.author_name} ` : '', spoilers: edit && comment.contains_spoilers, editing: edit ? comment : null, parent: edit ? comment.parent_comment_id : comment.parent_comment_id || comment.comment_id });
    setError(''); composer.current?.focus(); composer.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  const perform = async (action: () => Promise<unknown>, success?: () => void) => {
    if (busy.current) return;
    busy.current = true; setPending(true); setError('');
    try { await action(); if (alive.current) { success?.(); setRevision(value => value + 1); } }
    catch (err) { if (alive.current) setError(err instanceof Error ? err.message : 'Unable to complete this action. Please try again.'); }
    finally { busy.current = false; if (alive.current) setPending(false); }
  };
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (authLoading) return;
    if (!isAuthenticated) { navigate(loginDestination()); return; }
    if (!draft.text.trim()) return;
    void perform(() => draft.editing
      ? communityApi.updateComment(draft.editing.post_id, draft.editing.comment_id, { body_markdown: draft.text, expected_version: draft.editing.version_no, contains_spoilers: draft.spoilers })
      : postId ? apiClient.community.createComment(postId, draft.text, draft.parent || undefined, undefined, draft.spoilers, draft.key)
      : apiClient.proof.createProofComment(encodeURIComponent(proofId), { body_markdown: draft.text, parent_comment_id: draft.parent, contains_spoilers: draft.spoilers }, draft.key), () => { setDraft(emptyDraft()); try { sessionStorage.removeItem(storageKey); } catch {} });
  };
  const ordered = (items: Comment[]) => [...items].sort((a, b) => (Date.parse(a.created_at) - Date.parse(b.created_at)) * (sort === 'oldest' ? 1 : -1));
  const renderComment = (comment: Comment) => {
    const deleted = comment.status === 'DELETED';
    const masked = comment.is_spoiler_masked || comment.is_locked || comment.visibility === 'MASKED';
    const own = isAuthenticated && comment.author_id === user?.id;
    return <article className="proof-comment" key={comment.comment_id} data-testid={`comment-${comment.comment_id}`}>
      {!deleted && <header><strong>{comment.author_name || 'Viewer'}</strong><time dateTime={comment.created_at}>{new Date(comment.created_at).toLocaleDateString('en-US')}</time></header>}
      {deleted ? <p className="deleted-comment">This comment has been deleted.</p> : masked ? <CommentSpoiler canReveal={Boolean(comment.can_reveal)} pending={pending} inspectionStatus={comment.inspection_status} onReveal={() => void perform(() => communityApi.unlockContent('COMMENT', comment.comment_id, comment.version_no))} /> : <p className="comment-body">{comment.body_markdown}</p>}
      {!deleted && <div className="comment-actions"><button disabled={pending || authLoading} onClick={() => start(comment, false)}>Reply</button>{own && <><button disabled={pending || masked} onClick={() => start(comment, true)}>Edit</button><button disabled={pending} onClick={() => setDeleting(comment)}>Delete</button></>}</div>}
    </article>;
  };
  return <section className="proof-comments" aria-label="Comments">
    {deleting && <DeleteConfirmation kind="comment" detail="Replies will be kept." onCancel={() => setDeleting(null)} onDelete={async () => {
      await communityApi.deleteComment(deleting.post_id, deleting.comment_id);
      if (draft.editing?.comment_id === deleting.comment_id) setDraft(emptyDraft());
      setRevision(value => value + 1);
    }} />}
    <header className="comments-heading"><h2>Comments ({comments.filter(item => item.status !== 'DELETED').length})</h2><label>Sort <select value={sort} onChange={event => setSort(event.target.value)}><option value="oldest">Oldest first</option><option value="newest">Newest first</option></select></label></header>
    <form className="comment-composer" onSubmit={submit}>
      <label htmlFor={`comment-input-${proofId}`}>{draft.editing ? 'Edit comment' : draft.parent ? 'Write a reply' : 'Write a comment'}</label>
      <textarea ref={composer} id={`comment-input-${proofId}`} value={draft.text} maxLength={2000} disabled={pending} onChange={event => updateDraft({ text: event.target.value })} placeholder="Share your interpretation…" />
      <label className="comment-spoiler-check"><input type="checkbox" checked={draft.spoilers} disabled={pending} onChange={event => updateDraft({ spoilers: event.target.checked })} />Contains spoilers</label>
      <small>Your words stay unchanged. Possible spoilers and unchecked comments are blurred until each reader chooses to open them.</small>
      {error && <p role="alert">{error}</p>}
      <div className="comment-submit">{(dirty || draft.parent || draft.editing) && <button type="button" disabled={pending} onClick={() => { if (discard()) { setDraft(emptyDraft()); setError(''); } }}>Cancel</button>}<button type="submit" disabled={pending || authLoading || (isAuthenticated && !draft.text.trim())}>{pending ? 'Posting…' : !isAuthenticated ? 'Log In to Comment' : error ? 'Try Again' : draft.editing ? 'Save Changes' : draft.parent ? 'Post Reply' : 'Post Comment'}</button></div>
    </form>
    {loading && <p role="status">Loading comments…</p>}{loadError && <p role="alert">{loadError} <button onClick={() => setRevision(value => value + 1)}>Try Again</button></p>}
    {!loading && !loadError && !comments.length && <p className="comments-empty">No comments yet. Start the conversation.</p>}
    {ordered(comments.filter(item => !item.parent_comment_id)).map(root => <div className="comment-thread" key={root.comment_id}>{renderComment(root)}<div className="comment-replies">{ordered(comments.filter(item => item.parent_comment_id === root.comment_id)).map(renderComment)}</div></div>)}
  </section>;
}
