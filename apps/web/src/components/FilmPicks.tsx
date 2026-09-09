import React, { useEffect, useRef, useState } from 'react';
import { RankedFilmCard } from './RankedFilmCard';

export function FilmPicks({ films, navigate }: {
  films: { movieId: string; title: string; posterPath?: string | null; year?: number | string | null; destination?: string }[];
  navigate: (path: string) => void;
}) {
  const rail = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: true });
  const update = () => { const el = rail.current; if (el) setEdges({ start: el.scrollLeft < 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 }); };
  useEffect(() => {
    const el = rail.current; if (!el) return;
    const observer = new ResizeObserver(update); observer.observe(el); update();
    return () => observer.disconnect();
  }, [films.length]);
  const move = (direction: number) => {
    const el = rail.current; if (!el) return;
    el.scrollBy({ left: direction * ((el.firstElementChild?.getBoundingClientRect().width || 350) + 12),
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  };
  return <section className="home-top-box film-picks" aria-labelledby="film-picks-title">
    <h2 id="film-picks-title" className="catalog-section-title">RE:SCENE's PICK</h2>
    <div className="box-office-poster-row">
      <button className="poster-row-arrow picks-arrow" aria-label="Previous RE:SCENE picks" disabled={edges.start} onClick={() => move(-1)}>‹</button>
      <div className="box-office-poster-rail" ref={rail} onScroll={update} tabIndex={0} aria-label="RE:SCENE picks" onKeyDown={event => {
        if (event.target === event.currentTarget && ['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1); }
      }}>
        {films.slice(0, 10).map((film, index) => <RankedFilmCard key={film.movieId} title={film.title} rank={index + 1}
          posterPath={film.posterPath || undefined} badge="RE:SCENE Pick" testId={`film-card-${film.movieId}`}
          metadata={<><span>{film.year || ''}</span><span>Featured</span></>}
          onClick={() => navigate(film.destination || `/films/${encodeURIComponent(film.movieId)}`)} />)}
      </div>
      <button className="poster-row-arrow picks-arrow" aria-label="Next RE:SCENE picks" disabled={edges.end} onClick={() => move(1)}>›</button>
    </div>
  </section>;
}
