import React from 'react';

export function Pagination({ page, total, pageSize = 12, onChange }: { page: number; total: number; pageSize?: number; onChange: (page: number) => void }) {
  const count = Math.ceil(total / pageSize);
  if (count < 2) return null;
  return <nav aria-label="Movie pages" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 8, margin: '32px 0', width: '100%' }}>{Array.from({ length: count }, (_, index) => <button key={index} onClick={() => onChange(index + 1)} aria-current={page === index + 1 ? 'page' : undefined} style={{ minWidth: 40, height: 40, border: '1px solid #E6E6EA', borderRadius: 6, background: page === index + 1 ? '#4C22F4' : 'white', color: page === index + 1 ? 'white' : '#2D2D34', cursor: 'pointer', font: 'inherit' }}>{index + 1}</button>)}</nav>;
}
