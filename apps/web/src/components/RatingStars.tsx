import React from 'react';
import filled from '../assets/figma/rating-star-filled.svg';
import empty from '../assets/figma/rating-star-empty.svg';

export function RatingStars({ rating }: { rating: number }) {
  const safeRating = Math.max(0, Math.min(5, Math.round(rating)));
  return <span role="img" aria-label={`${safeRating} out of 5 stars`} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>{Array.from({ length: 5 }, (_, index) => <img key={index} src={index < safeRating ? filled : empty} alt="" width={24} height={24} />)}<span aria-hidden="true" style={{ marginLeft: 6, color: '#AFAFB8', fontSize: 16 }}>{safeRating}</span></span>;
}
