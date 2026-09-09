import React from 'react';

// Original pages and bylines checked 2026-09-09. No audience ratings or AI text relabelled as critics.
const reviews: Record<string, { title: string; date: string; url: string }> = {
  'the-greene-murder-case-1929': { title: 'The Greene Murder Case (1929)', date: 'July 30, 2020', url: 'https://www.franksmovielog.com/reviews/the-greene-murder-case-1929/' },
  'the-thirteenth-chair-1929': { title: 'The Thirteenth Chair (1929)', date: 'November 13, 2025', url: 'https://www.franksmovielog.com/reviews/the-thirteenth-chair-1929/' },
};

export function ExternalCriticism({ movieId }: { movieId: string }) {
  const review = reviews[movieId];
  if (!review) return null;
  return <section className="external-criticism" aria-labelledby="external-criticism-title">
    <h2 id="external-criticism-title">External Criticism</h2>
    <p>Independent writing, separate from RE:SCENE audience reviews and AI analysis. The linked review may contain spoilers.</p>
    <article><h3>{review.title}</h3><p>Frank Showalter · Frank’s Movie Log · {review.date}</p>
      <a href={review.url} target="_blank" rel="noopener noreferrer">Read the original review ↗</a>
    </article>
  </section>;
}
