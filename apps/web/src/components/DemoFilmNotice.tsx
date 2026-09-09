import React from 'react';
import { FilmCatalogItemViewModel } from '../pages/filmCatalogViewModel';

// Rights research: docs/public-domain-demo-selection.md.
// Selection is not analysis readiness. Never promote these to READY from this UI.
const selectedTitles = [
  { movieId: 'the-greene-murder-case-1929', title: 'The Greene Murder Case (1929)', source: 'https://catalog.afi.com/Catalog/moviedetails/9512' },
  { movieId: 'the-thirteenth-chair-1929', title: 'The Thirteenth Chair (1929)', source: 'https://catalog.afi.com/Film/12638-THE-THIRTEENTH-CHAIR' },
];

export function DemoFilmNotice({ films, navigate }: {
  films: FilmCatalogItemViewModel[]; navigate?: (path: string) => void;
}) {
  const available = films.filter(film => film.coreDemoSupported === true);
  const pending = selectedTitles.filter(selected => !available.some(film => film.movieId === selected.movieId));
  return <div className="demo-film-notice-copy">
    <div>Core analysis demos: {available.length ? available.map((film, index) => <React.Fragment key={film.movieId}>
      {index > 0 && ' · '}
      <a href={film.destination} onClick={event => {
        if (navigate) { event.preventDefault(); navigate(film.destination); }
      }}>{film.title}{film.year ? ` (${film.year})` : ''}</a>
    </React.Fragment>) : 'No ready titles are currently listed.'}</div>
    {pending.length > 0 && <div data-testid="demo-selected-titles">Selected U.S. public-domain originals — analysis not yet available: {pending.map((film, index) => <React.Fragment key={film.title}>
      {index > 0 && ' · '}
      <a href={film.source} target="_blank" rel="noopener noreferrer">{film.title} ↗</a>
    </React.Fragment>)}. Later additions require a separate rights review.</div>}
  </div>;
}
