import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { useAuth } from '../context/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '../components/FeedbackStates';
import type { CommunityPostDTO } from '../types/api';

export function LiveCommunityPage({ navigate }: { navigate: (path: string) => void }) {
  const { isAuthenticated } = useAuth();
  const [posts, setPosts] = useState<CommunityPostDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState('');
  const [oldestFirst, setOldestFirst] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError('');
    apiClient.community.listPosts().then(response => {
      if (!cancelled) setPosts(response.data);
    }).catch(reason => {
      if (!cancelled) setError(reason.message || 'Failed to load community posts.');
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isAuthenticated, reload]);
  const filtered = posts.filter(post => (post.title || '').toLowerCase().includes(query.trim().toLowerCase()));
  const visible = oldestFirst ? [...filtered].reverse() : filtered;
  return <section className="live-community">
    <header>
      <h1>Community</h1>
      <p>Share scene evidence and reframed interpretations for The Bat Whispers. Content is spoiler-protected based on your viewing progress.</p>
      <div className="journey-actions">
        <button onClick={() => navigate('/films/the-bat-whispers-1930')}>Film & Viewing Progress</button>
        <button onClick={() => setReload(value => value + 1)}>Refresh</button>
      </div>
    </header>
    <div className="community-filters">
      <label>Search posts by title<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Filter discussions..." /></label>
      <label>Sort<select value={oldestFirst ? 'oldest' : 'latest'} onChange={event => setOldestFirst(event.target.value === 'oldest')}><option value="latest">Newest First</option><option value="oldest">Oldest First</option></select></label>
    </div>
    {loading ? <LoadingState message="Loading community posts..." /> : error ? <ErrorState message={error} /> : <>
      <p role="status">Total {visible.length} posts{query ? ` (of ${posts.length} total)` : ''}</p>
      {!visible.length && <EmptyState title="No posts found" message="Try a different search query or check back later." />}
      {visible.map(post => <article key={post.post_id}>
        <span className="community-category">{post.is_locked ? 'Spoiler Protected' : 'Film Interpretation'}</span>
        <h2><button onClick={() => navigate(`/posts/${post.post_id}`)}>{post.title || 'Spoiler Protected Post'}</button></h2>
        <p>{post.is_locked ? 'Confirm your viewing progress to read the full analysis and counter-arguments.' : post.body_markdown?.slice(0, 240)}</p>
        <small>{post.author_name || ''}</small>
      </article>)}
    </>}
  </section>;
}
