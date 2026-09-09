import React from 'react';

export function NoticePage({ navigate }: { navigate: (path: string) => void }) {
  return (
    <section className="notice-page" style={{ maxWidth: 960, margin: '40px auto', padding: '0 24px', color: '#2D2D34' }}>
      <h1>Notice</h1>
      <article>
        <h2>Explore films without unwanted spoilers</h2>
        <p>Choose a movie and set your viewing progress. Reveal markers select an interpretation; they do not change your viewing progress or unlock later spoilers.</p>
        <p>Log in to write reviews and replies. Spoiler-protected replies cannot be manually revealed.</p>
        <p>Available analysis and media vary by film and edition. Unavailable material is marked as in preparation.</p>
        <button type="button" onClick={() => navigate('/films')}>Explore Movies</button>
      </article>
    </section>
  );
}
