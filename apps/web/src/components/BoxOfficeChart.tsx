import React, { useEffect, useMemo, useRef, useState } from 'react';
import { findPublicFilmIntroductions, selectChartFilm } from '../services/boxOfficeFilm';
import { RankedFilmCard } from './RankedFilmCard';

const FEED = 'https://www.boxofficemojo.com/data/js/wknd5.php';
interface ChartFilm { title: string; gross: string; posterUrl?: string; pageId?: number }

// Read plain chart data from an opaque-origin frame. Provider code stays isolated.
function chartDocument(channel: string): string {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${channel}' ${FEED}; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
</head><body><script src="${FEED}" referrerpolicy="no-referrer"></script>
<script nonce="${channel}">
(() => {
 const cells = Array.from(document.querySelectorAll('td.mojo_row'));
 const films = cells.filter((_, i) => i % 2 === 0).map((cell, i) => ({
   title: cell.textContent.trim().replace(/^\\d+\\.\\s*/, ''), gross: cells[i*2+1]?.textContent.trim()
 }));
 const valid = cells.length === 10 && films.every((film, i) => cells[i*2].textContent.trim().startsWith((i+1)+'. ') && film.title && film.gross);
 parent.postMessage({channel:'${channel}', type:valid?'ready':'unavailable', films,
   period:document.querySelector('.mojo_header')?.textContent.trim() || ''}, '*');
})();
</script></body></html>`;
}

export const BoxOfficeChart: React.FC<{ navigate: (path: string) => void }> = ({ navigate }) => {
  const frame = useRef<HTMLIFrameElement>(null), rail = useRef<HTMLDivElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [films, setFilms] = useState<ChartFilm[]>([]);
  const [edges, setEdges] = useState({ start: true, end: false });
  const channel = useMemo(() => crypto.randomUUID().replace(/-/g, ''), [attempt]);
  const document = useMemo(() => chartDocument(channel), [channel]);
  const updateEdges = () => { const el = rail.current; if (el) setEdges({ start: el.scrollLeft < 1, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 1 }); };

  useEffect(() => {
    setState('loading'); setFilms([]);
    const controller = new AbortController();
    let posterTimeout: number | undefined;
    let received = false;
    const timeout = window.setTimeout(() => { received = true; setState('unavailable'); }, 15000);
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || event.origin !== 'null' ||
          !event.data || event.data.channel !== channel || received) return;
      const data = event.data;
      const validText = (value: unknown, max: number) => typeof value === 'string' && value.trim().length > 0 && value.length <= max && !/[\u0000-\u001f]/.test(value);
      received = true; window.clearTimeout(timeout);
      if (data.type !== 'ready' || !Array.isArray(data.films) || data.films.length !== 5 ||
          !data.films.every((film: ChartFilm) => film && validText(film.title, 200) && validText(film.gross, 60)) || !validText(data.period, 200)) {
        setState('unavailable'); return;
      }
      const entries: ChartFilm[] = data.films.map((film: ChartFilm) => ({ title: film.title, gross: film.gross }));
      setFilms(entries); setState('ready');
      posterTimeout = window.setTimeout(() => controller.abort(), 12000);
      Promise.all(entries.map(async film => {
        try {
          const matches = await findPublicFilmIntroductions(film.title, controller.signal);
          const match = selectChartFilm(film.title, data.period, matches);
          if (match && !controller.signal.aborted) {
            setFilms(current => current.map(item => item.title === film.title ? { ...item, posterUrl: match.posterUrl, pageId: match.pageId } : item));
          }
        } catch { /* Preserve the real rank/title without an unrelated poster. */ }
      })).finally(() => window.clearTimeout(posterTimeout));
    };
    window.addEventListener('message', receive);
    const refresh = window.setInterval(() => { if (!window.document.hidden) setAttempt(value => value + 1); }, 3600000);
    return () => { controller.abort(); window.clearTimeout(posterTimeout); window.clearTimeout(timeout); window.clearInterval(refresh); window.removeEventListener('message', receive); };
  }, [channel]);

  useEffect(() => {
    const el = rail.current; if (!el) return;
    const observer = new ResizeObserver(updateEdges); observer.observe(el); updateEdges();
    return () => observer.disconnect();
  }, [state]);

  const move = (direction: number) => {
    const el = rail.current; if (!el) return;
    const step = (el.firstElementChild?.getBoundingClientRect().width || 350) + 12;
    el.scrollTo({ left: direction < 0 ? 0 : el.scrollLeft + step, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  };
  return <section data-testid="home-top-box" className="home-top-box" aria-labelledby="top-box-title">
    <h2 id="top-box-title" className="catalog-section-title">TOP BOX</h2>
    {state === 'loading' && <p role="status">Loading the latest weekend chart…</p>}
    <iframe key={channel} ref={frame} title="Box Office Mojo weekend Top 5" srcDoc={document} hidden
      sandbox="allow-scripts" referrerPolicy="no-referrer" />
    {state === 'ready' && <>
      <div className="box-office-poster-row">
        <div className="box-office-poster-rail" ref={rail} onScroll={updateEdges}>
          {films.map((film, index) => <RankedFilmCard key={film.title} title={film.title} rank={index + 1}
            posterPath={film.posterUrl} badge="Weekend Top 5" testId={`top-box-film-${index + 1}`}
            metadata={<><span>{film.gross}</span><span>Weekend gross</span></>}
            onClick={() => navigate(`/box-office/film?title=${encodeURIComponent(film.title)}${film.pageId ? `&pageId=${film.pageId}` : ''}`)} />)}
        </div>
        {(!edges.end || !edges.start) && <button className="poster-row-arrow" aria-label={edges.end ? 'Back to first TOP BOX films' : 'Next TOP BOX films'}
          onClick={() => move(edges.end ? -1 : 1)}><CatalogArrow previous={edges.end} /></button>}
      </div>
    </>}
    {state === 'unavailable' && <div role="status" className="box-office-unavailable">
      <p>The weekend chart is temporarily unavailable. No substitute rankings are shown.</p>
      <button type="button" onClick={() => setAttempt(value => value + 1)}>Try again</button>
      {' '}<a href="https://www.boxofficemojo.com/weekend/" target="_blank" rel="noopener noreferrer">View the source chart ↗</a>
    </div>}
  </section>;
};

// Reuse the existing Browse Films chevron artwork.
function CatalogArrow({ previous = false }: { previous?: boolean }) {
  return <svg aria-hidden="true" width="100%" height="100%" viewBox="0 0 60 437" fill="none" style={{ transform: previous ? 'rotate(180deg)' : undefined }}>
    <path d="M26 226.5L34 218.5L26 210.5" stroke="var(--Gray-700, #4A4A53)" strokeWidth="2.66667" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}
