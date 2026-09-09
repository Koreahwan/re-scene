import React from 'react';
import { ReframeCardViewModel } from '../pages/filmDetailViewModel';
import './WatchedAnalysisCard.css';

export function WatchedAnalysisCard({ card, index, navigate }: {
  card: ReframeCardViewModel; index: number; navigate: (path: string) => void;
}) {
  return <article className="watched-analysis-card" data-testid={`film-detail-reframe-card-${index}`}>
    <header className="watched-analysis-card-meta">
      {card.scene && <span>{card.scene}</span>}
      {card.timestamp && <span data-testid={`film-detail-reframe-time-${index}`}>{card.timestamp}</span>}
    </header>
    <h3>{card.title}</h3>
    <p>{card.body}</p>
    <footer>
      <button type="button" data-testid={`film-detail-reframe-more-${index}`}
        aria-label={`View analysis: ${card.title}`}
        onClick={() => navigate(`/proofs/${encodeURIComponent(card.id)}`)}>View analysis</button>
    </footer>
  </article>;
}
