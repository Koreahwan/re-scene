import React, { useEffect, useRef, useState } from 'react';
import { RevealItemViewModel } from '../pages/filmDetailViewModel';

export function RevealTimelineMarkers({ reveals, runtimeMs, selectedId, onSelect }: {
  reveals: RevealItemViewModel[]; runtimeMs: number; selectedId: string | null;
  onSelect: (reveal: RevealItemViewModel) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1680);
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  const laneEnds: number[] = [];
  const markers = reveals.map((reveal, index) => ({ reveal, index }))
    .sort((a, b) => a.reveal.timestampMs - b.reveal.timestampMs)
    .map(({ reveal, index }) => {
      const position = Math.max(0, Math.min(1, reveal.timestampMs / Math.max(1, runtimeMs)));
      const x = Math.max(0, Math.min(Math.max(0, width - 104), position * width - 52));
      let lane = laneEnds.findIndex(end => x >= end + 8);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = x + 104;
      return { reveal, index, x, lane, position };
    });
  return <div ref={ref} data-testid="film-detail-reframe-marker-row"
    style={{ position: 'relative', width: '100%', height: Math.max(36, laneEnds.length * 36) }}>
    {markers.map(({ reveal, index, x, lane, position }) => <React.Fragment key={reveal.revealId}>
      <span aria-hidden="true" style={{ position: 'absolute', left: `${position * 100}%`,
        top: lane * 36 + 30, bottom: 0, width: 1, background: '#DCD6F7' }} />
      <button type="button" data-testid={`film-detail-reframe-marker-${index}`}
        aria-label={`Inspect reveal at ${reveal.timestampDisplay}`}
        aria-pressed={selectedId === reveal.revealId} onClick={() => onSelect(reveal)}
        style={{ position: 'absolute', left: x, top: lane * 36, width: 104, height: 32,
          display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: 0,
          border: 0, background: 'transparent', color: selectedId === reveal.revealId ? '#4C22F4' : '#898992',
          cursor: 'pointer', fontSize: 12, fontWeight: selectedId === reveal.revealId ? 600 : 400 }}>
        <img src="/assets/figma-current/film-detail/reframe/reveal-marker.svg" alt="" width={14} height={13}
          style={{ position: 'absolute', left: position * width - x - 7, bottom: 0, transform: 'rotate(180deg)' }} />
        {reveal.timestampDisplay}
      </button>
    </React.Fragment>)}
  </div>;
}
