import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { profileApi, MyReviewDTO, WishlistFilmDTO } from '../services/apiClient';
import { AppModal } from '../components/AppModal';
import { useUnsavedChanges } from '../utils/useUnsavedChanges';
import { loginDestination } from '../utils/navigation';
import './MyPage.css';
import defaultAvatar from '../assets/images/avatar_default.png';
import { RatingStars } from '../components/RatingStars';

export function MyPage({ navigate }: { navigate: (path: string) => void }) {
  const { user, isAuthenticated, loading: authLoading, refreshUser } = useAuth();
  const [tab, setTab] = useState<'reviews' | 'wishlist'>('reviews');
  const [page, setPage] = useState(1);
  const [reviews, setReviews] = useState<MyReviewDTO[]>([]);
  const [wishlist, setWishlist] = useState<WishlistFilmDTO[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [removed, setRemoved] = useState<WishlistFilmDTO | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const mutation = useRef(false);
  const [editing, setEditing] = useState(false);
  const [nickname, setNickname] = useState('');
  const [photo, setPhoto] = useState<string | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState('');
  const dirty = editing && (nickname !== user?.display_name || photo !== undefined);
  useUnsavedChanges(dirty);

  useEffect(() => {
    if (!isAuthenticated) { setLoading(false); return; }
    let active = true;
    setLoading(true); setError('');
    const request = tab === 'reviews' ? profileApi.getMyReviews(page) : profileApi.getWishlist(page);
    request.then(result => {
      if (!active) return;
      if (tab === 'reviews') setReviews(result.data as MyReviewDTO[]);
      else setWishlist(result.data);
      setTotal(result.meta.total);
      if (page > 1 && !result.data.length) setPage(page - 1);
    }).catch(() => { if (active) setError('Unable to load your list. Please try again.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [isAuthenticated, user?.id, tab, page, revision]);

  useEffect(() => {
    if (!removed) return;
    const timer = window.setTimeout(() => setRemoved(null), 8000);
    return () => window.clearTimeout(timer);
  }, [removed]);

  const updateWishlist = async (film: WishlistFilmDTO, saved: boolean) => {
    if (mutation.current) return;
    mutation.current = true; setPending(film.movie_id); setError('');
    const previous = wishlist;
    if (!saved) setWishlist(items => items.filter(item => item.movie_id !== film.movie_id));
    try {
      await profileApi.setWishlist(film.movie_id, saved);
      setRemoved(saved ? null : film);
      setRevision(value => value + 1);
    } catch {
      setWishlist(previous);
      setError(saved ? 'Unable to restore this film. Try Undo again.' : 'Unable to remove this film. Your Wishlist has not changed.');
    } finally { mutation.current = false; setPending(null); }
  };

  const closeEditor = () => {
    if (saving || (dirty && !window.confirm('Discard your unsaved changes?'))) return;
    setEditing(false);
  };

  const choosePhoto = (file?: File) => {
    if (!file) return;
    if (file.size > 1_000_000 || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setEditError('Choose a PNG, JPEG or WebP photo under 1 MB and 4 megapixels.'); return;
    }
    const reader = new FileReader();
    reader.onload = () => { setPhoto(String(reader.result)); setEditError(''); };
    reader.onerror = () => setEditError('Unable to read this photo. Choose it again.');
    reader.readAsDataURL(file);
  };

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (mutation.current || !nickname.trim()) return;
    mutation.current = true; setSaving(true); setEditError('');
    try {
      await profileApi.updateProfile({ display_name: nickname.trim(), ...(photo !== undefined ? { photo_data: photo } : {}) });
      setEditing(false); await refreshUser();
    } catch (err) { setEditError(err instanceof Error ? err.message : 'Unable to save your profile. Try again.'); }
    finally { mutation.current = false; setSaving(false); }
  };

  if (authLoading) return <main className="my-page"><p role="status">Loading your profile…</p></main>;
  if (!isAuthenticated) return <main className="my-page"><h1>My Page</h1><p>Log in to see your reviews and Wishlist.</p><button onClick={() => navigate(loginDestination('/me'))}>Log In</button></main>;

  return <main className="my-page">
    <h1>My Page</h1>
    <section className="my-profile" aria-label="Your profile">
      <img className="profile-photo" src={user?.avatar_url || defaultAvatar} alt="Your profile" />
      <h2>{user?.display_name}</h2>
      <button onClick={() => { setNickname(user?.display_name || ''); setPhoto(undefined); setEditError(''); setEditing(true); }}>Edit Profile</button>
    </section>
    <nav className="my-tabs" aria-label="My lists">{(['reviews', 'wishlist'] as const).map(value => <button key={value} aria-current={tab === value ? 'page' : undefined} onClick={() => { setTab(value); setPage(1); }}>{value === 'reviews' ? 'My Reviews' : 'Wishlist'}</button>)}</nav>
    {error && <p role="alert">{error} <button onClick={() => setRevision(value => value + 1)}>Try Again</button></p>}
    {loading ? <p role="status">Loading…</p> : !error && !total ? <section className="my-empty"><h2>{tab === 'reviews' ? 'No reviews yet' : 'Your Wishlist is empty'}</h2><p>{tab === 'reviews' ? 'Share your thoughts after exploring a film.' : 'Save films you want to explore from their detail page.'}</p><button onClick={() => navigate('/films')}>Explore Movies</button></section> : <>
      {tab === 'reviews' ? <div className="my-reviews">{reviews.map(review => <button className="my-review" key={review.post_id} onClick={() => navigate(review.destination || `/films/${encodeURIComponent(review.movie_id)}?reviewId=${encodeURIComponent(review.post_id)}`)}>
        {review.poster_path && <img src={review.poster_path} alt="" />}<span><RatingStars rating={review.rating} /><strong>{review.title}</strong><span className="review-excerpt">{review.body_markdown}</span><time dateTime={review.created_at}>{new Date(review.created_at).toLocaleDateString('en-US')}</time></span>
      </button>)}</div> : <div className="my-wishlist">{wishlist.map(film => <article key={film.movie_id}><button className="wishlist-film" onClick={() => navigate(`/films/${encodeURIComponent(film.movie_id)}`)}>{film.poster_path && <img src={film.poster_path} alt="" />}<strong>{film.title}</strong></button><button disabled={pending !== null} onClick={() => updateWishlist(film, false)} aria-label={`Remove ${film.title} from Wishlist`}>Remove</button></article>)}</div>}
      {total > 12 && <nav className="my-pagination" aria-label="List pages">{Array.from({ length: Math.ceil(total / 12) }, (_, index) => <button key={index} aria-current={page === index + 1 ? 'page' : undefined} onClick={() => setPage(index + 1)}>{index + 1}</button>)}</nav>}
    </>}
    {removed && <div className="wishlist-undo" role="status">Removed from Wishlist · <button disabled={pending !== null} onClick={() => updateWishlist(removed, true)}>Undo</button></div>}
    <AppModal isOpen={editing} onClose={closeEditor} title="Edit Profile" size="sm"><form className="profile-form" onSubmit={saveProfile}>
      <label>Nickname<input value={nickname} maxLength={100} required disabled={saving} onChange={event => setNickname(event.target.value)} /></label>
      <label>Profile photo<input type="file" accept="image/png,image/jpeg,image/webp" disabled={saving} onChange={event => choosePhoto(event.target.files?.[0])} /></label>
      {(photo || (photo === undefined && user?.avatar_url)) && <img className="profile-photo" src={photo || user?.avatar_url || ''} alt="Profile preview" />}
      <small>PNG, JPEG or WebP. Under 1 MB and 4 megapixels.</small><button type="button" disabled={saving} onClick={() => setPhoto(null)}>Remove photo</button>
      {editError && <p role="alert">{editError}</p>}<div><button type="button" disabled={saving} onClick={closeEditor}>Cancel</button><button type="submit" disabled={saving || !nickname.trim() || !dirty}>{saving ? 'Saving…' : editError ? 'Try Again' : 'Save Changes'}</button></div>
    </form></AppModal>
  </main>;
}
