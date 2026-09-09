import React, { useEffect, useRef, useState } from 'react';
import { filmsApi } from '../services/apiClient';
import { SelectedPortion, PortionSegment, validateSelectedPortion } from '../services/selectedPortion';
import { formatTimestampMs } from '../pages/filmDetailViewModel';
import './SelectedPortionAnalysis.css';

export function SelectedPortionAnalysis({ movieId, editionId, positionMs, disabled, viewerKey }: {
  movieId: string; editionId: string; positionMs: number; disabled: boolean; viewerKey: string;
}) {
  const owner = `${movieId}:${editionId}:${positionMs}:${viewerKey}`;
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const request = useRef<AbortController | null>(null);
  const [openedFor, setOpenedFor] = useState<string | null>(null);
  const [result, setResult] = useState<{ owner: string; data: SelectedPortion } | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const open = openedFor === owner && !disabled;

  useEffect(() => {
    request.current?.abort();
    setOpenedFor(null); setResult(null); setError(''); setLoading(false);
    return () => request.current?.abort();
  }, [owner, disabled]);

  async function toggle() {
    request.current?.abort();
    if (open) { setOpenedFor(null); setResult(null); setError(''); setLoading(false); return; }
    const controller = new AbortController();
    request.current = controller;
    const requestedOwner = owner;
    setOpenedFor(owner); setResult(null); setError(''); setLoading(true);
    try {
      const response = await filmsApi.getSelectedPortion(movieId, editionId, positionMs, controller.signal);
      if (controller.signal.aborted || ownerRef.current !== requestedOwner) return;
      setResult({ owner: requestedOwner, data: validateSelectedPortion(response.data, movieId, editionId, positionMs) });
    } catch (failure) {
      if (!controller.signal.aborted && ownerRef.current === requestedOwner) {
        setError(failure instanceof Error ? failure.message : 'Could not load this portion.');
      }
    } finally {
      if (!controller.signal.aborted && ownerRef.current === requestedOwner) setLoading(false);
    }
  }

  const data = open && result?.owner === owner ? result.data : null;
  const segments = [...(data?.segments || [])].reverse();
  const renderSegment = (segment: PortionSegment) => <article className="portion-analysis-card" key={segment.segment_id}
    data-testid={`portion-segment-${segment.segment_id}`}>
    <header>{formatTimestampMs(segment.start_ms)}–{formatTimestampMs(segment.end_ms)}</header>
    <h3>Reading this segment</h3>
    <p>{segment.summary}</p>
    <p className="portion-reading">{segment.reading}</p>
    <details>
      <summary>Observations from this segment ({segment.observations.length})</summary>
      <ul>{segment.observations.map((observation, index) => <li key={`${observation.timestamp_ms}:${index}`}>
        <span>{formatTimestampMs(observation.timestamp_ms)}</span> {observation.text}
        {observation.uncertainty && !['None', 'Sampled stills; dialogue is not established.'].includes(observation.uncertainty.trim()) && <small>{observation.uncertainty}</small>}
      </li>)}</ul>
    </details>
    <small style={{ display: 'block', marginTop: 16, marginBottom: 16, lineHeight: 1.6 }}>{segment.source_method === 'SAMPLED_STILLS_ONLY'
      ? 'Gemini · sampled images only; no dialogue verification.'
      : 'Gemini · segment audio and sampled images.'} AI observations, not human reviewed.</small>
  </article>;

  return <section className="selected-portion-analysis" aria-labelledby="selected-portion-heading">
    <h2 id="selected-portion-heading">Analysis up to your selected point</h2>
    <p>Only completed source segments at or before {formatTimestampMs(positionMs)}. No later reinterpretations are included.</p>
    <button type="button" className="watched-analysis-toggle" data-testid="selected-portion-analysis-toggle"
      disabled={disabled} aria-expanded={open} aria-controls="selected-portion-content" onClick={() => void toggle()}>
      {open ? 'Hide selected-portion analysis' : 'Show analysis up to selected point'}
    </button>
    {open && <div id="selected-portion-content" data-testid="selected-portion-content" aria-busy={loading}>
      {loading && <p role="status">Loading this viewing portion…</p>}
      {error && <p role="alert">{error} Close and reopen to try again.</p>}
      {data && <>
        <p className="portion-coverage">Prepared observations cover through {formatTimestampMs(data.covered_until_ms)}.
          {' '}A partially watched source segment stays excluded until its whole input window has been seen.</p>
        {segments.length === 0 ? <p>No completed prepared segment at this point yet. Nothing from a later segment has been loaded.</p> : <>
          <div className="portion-analysis-grid">{segments.slice(0, 3).map(renderSegment)}</div>
          {segments.length > 3 && <details className="portion-earlier"><summary>Earlier watched segments ({segments.length - 3})</summary>
            <div className="portion-analysis-grid">{segments.slice(3).map(renderSegment)}</div>
          </details>}
        </>}
      </>}
    </div>}
  </section>;
}
