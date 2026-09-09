import React, { useEffect, useState } from 'react';
import { findPublicFilmIntroductions, PublicFilmIntroduction } from '../services/boxOfficeFilm';
import topBoxMetadata from '../services/topBoxMetadata.json';
import { TopBoxReviews } from '../components/TopBoxReviews';

type ReleaseMetadata = { title: string; directors: { qid: string; name: string }[]; cast: { qid: string; name: string }[]; runtimeMinutes: number | null; sourceUrl: string };

export const BoxOfficeFilmPage: React.FC<{ title: string; pageId?: string | null; navigate: (path: string) => void }> = ({ title, pageId, navigate }) => {
  const [films, setFilms] = useState<PublicFilmIntroduction[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [attempt, setAttempt] = useState(0);
  const [reviewRequest, setReviewRequest] = useState(0);
  const validTitle = title.trim().length > 0 && title.length <= 200 && !/[\u0000-\u001f]/.test(title);

  useEffect(() => {
    const controller = new AbortController();
    setFilms([]); setSelected(null); setRevealed(false); setReviewRequest(0); setStatus('loading');
    if (!validTitle) { setStatus('error'); return () => controller.abort(); }
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    findPublicFilmIntroductions(title, controller.signal).then(results => {
      if (!active) return;
      const requested = results.find(item => String(item.pageId) === pageId);
      setFilms(results); setSelected(requested?.pageId ?? (results.length === 1 ? results[0].pageId : null)); setStatus('ready');
    }).catch(() => { if (active) setStatus('error'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [title, pageId, validTitle, attempt]);

  const film = films.find(item => item.pageId === selected);
  const metadata = film ? (topBoxMetadata as Record<string, ReleaseMetadata>)[String(film.pageId)] : undefined;
  return <main className="box-office-film-page" data-testid="box-office-film-detail">
    <button type="button" onClick={() => navigate('/films')}>← Back to TOP BOX</button>
    <header className="top-box-detail-hero" data-testid="film-detail-hero">
      <div className="top-box-detail-backdrop" aria-hidden="true" />
      <div className="top-box-detail-hero-content" data-testid="film-detail-hero-content">
        {film?.posterUrl ? <img className="top-box-detail-poster" data-testid="film-detail-poster" src={film.posterUrl} alt={`${film.title} English poster`} />
          : <div className="top-box-detail-poster top-box-poster-unavailable">{film ? 'English poster unavailable' : 'Choose a release to view its poster'}</div>}
        <div className="top-box-detail-meta" data-testid="film-detail-meta">
          <p className="box-office-eyebrow">TOP BOX · FILM DETAILS</p>
          <h1 data-testid="film-detail-title">{film?.title || (validTitle ? title : 'Film unavailable')}</h1>
          {film?.description && <p className="top-box-detail-description">{film.description}</p>}
          {metadata && <p className="top-box-detail-description">{metadata.runtimeMinutes ? `${metadata.runtimeMinutes}min` : ''}{metadata.directors.length ? `${metadata.runtimeMinutes ? ' · ' : ''}Director: ${metadata.directors.map(person => person.name).join(', ')}` : ''}</p>}
          <p className="top-box-detail-summary">{film ? 'Explore this release below. The introduction is hidden until you choose to read it.' : 'Film information is matched to the exact release, not just its title.'}</p>
        </div>
        <button type="button" className="top-box-review-button" disabled={!film || !metadata} onClick={() => { setReviewRequest(value => value + 1); document.querySelector('.top-box-reviews')?.scrollIntoView({ behavior: 'smooth' }); }}><img src="/assets/catalog/topbox-review-edit.svg" alt="" width={24} height={24} />Write a Review</button>
      </div>
    </header>
    {status === 'loading' && <p role="status">Loading film information…</p>}
    {status === 'error' && <div role="status"><p>Film information is temporarily unavailable.</p>
      {validTitle && <button type="button" onClick={() => setAttempt(value => value + 1)}>Try again</button>}</div>}
    {status === 'ready' && films.length === 0 && <p>No matching film information could be verified. We have not substituted another title.</p>}
    {films.length > 1 && <section aria-label="Choose the matching film"><h2>Which release?</h2>
      <p>Several films share this title. Choose the release to avoid showing the wrong information.</p>
      <div className="box-office-film-choices">{films.map(item => <button key={item.pageId} type="button"
        aria-pressed={selected === item.pageId} onClick={() => { setSelected(item.pageId); setRevealed(false); setReviewRequest(0); }}>
        {item.title}{item.description && <small>{item.description}</small>}
      </button>)}</div>
    </section>}
    {film && <section><h2>Cast &amp; Crew</h2>
      {metadata?.cast.length ? <><div className="top-box-cast-grid">{metadata.cast.map(person => <div className="top-box-cast-member" key={person.qid}><strong>{person.name}</strong><span>Cast</span></div>)}</div>
        <p className="box-office-attribution">Selected credits · <a href={metadata.sourceUrl} target="_blank" rel="noopener noreferrer">Wikidata · CC0 ↗</a></p></> : <p>Verified credits are not available for this release.</p>}
    </section>}
    {film && <section className="box-office-introduction"><h2>Synopsis</h2>
      {film.extract ? <><p>The introduction may include plot details.</p>
        <button type="button" aria-expanded={revealed} onClick={() => setRevealed(value => !value)}>
          {revealed ? 'Hide introduction' : 'Show introduction · may contain spoilers'}
        </button>
        {revealed && <p className="box-office-extract">{film.extract}</p>}
      </> : <p>An introduction is not available from this source.</p>}
      <p className="box-office-attribution">Film text: <a href={film.sourceUrl} target="_blank" rel="noopener noreferrer">Wikipedia contributors ↗</a>
        {' · '}<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>. Introduction excerpt; no rewriting.
      </p>
    </section>}
    <section className="box-office-analysis-notice"><h2>RE:FRAME</h2>
      <p>Scene analysis and video playback have not been published for this release.</p>
      <button type="button" onClick={() => navigate('/films')}>Explore the RE:FRAME catalog →</button>
    </section>
    {film && <TopBoxReviews key={film.pageId} pageId={film.pageId} title={film.title} navigate={navigate} openRequest={reviewRequest} />}
  </main>;
};
