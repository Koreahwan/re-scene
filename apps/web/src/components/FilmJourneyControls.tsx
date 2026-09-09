import React, { useState, useEffect, useRef } from 'react';
import { profileApi } from '../services/apiClient';
import { RevealItemViewModel, formatTimestampMs } from '../pages/filmDetailViewModel';
import '../styles/watch-timeline.css';

export function FilmJourneyControls({
  movieId,
  editionId,
  runtimeMs,
  reveals,
  children,
  initialProgressMs = 0,
  onProgressChange,
  onProgressPreview,
  onSavingChange,
}: {
  movieId: string;
  editionId: string;
  runtimeMs: number;
  reveals: RevealItemViewModel[];
  children?: React.ReactNode;
  initialProgressMs?: number;
  onProgressChange: () => void;
  onProgressPreview?: (ms: number) => void;
  onSavingChange?: (saving: boolean) => void;
}) {
  const duration = editionId && Number.isFinite(runtimeMs) && runtimeMs > 0 ? runtimeMs : 0;
  const clamp = (ms: number) => Math.max(0, Math.min(duration, Number.isFinite(ms) ? ms : 0));
  const [selectedProgress, setSelectedProgress] = useState(clamp(initialProgressMs));
  const [failed, setFailed] = useState(false);
  const latest = useRef<number | null>(null);
  const pending = useRef<number | null>(null);
  const saving = useRef(false);
  const mounted = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const callbacks = useRef({ onProgressChange, onSavingChange });
  callbacks.current = { onProgressChange, onSavingChange };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimeout(timer.current);
      // Metadata/auth refresh can remount this control during a save. The old
      // instance no longer owns the parent's busy indicator after unmount.
      callbacks.current.onSavingChange?.(false);
    };
  }, []);

  useEffect(() => {
    latest.current = null;
    pending.current = null;
    const initial = clamp(initialProgressMs);
    setSelectedProgress(initial);
  }, [movieId, editionId]);

  useEffect(() => {
    if (latest.current === null) {
      const initial = clamp(initialProgressMs);
      setSelectedProgress(initial);
    }
  }, [initialProgressMs, duration]);

  // Serialize writes so a slower earlier drag cannot overwrite the final position.
  const flush = async () => {
    clearTimeout(timer.current);
    if (saving.current || pending.current === null || !duration) return;
    saving.current = true;
    while (mounted.current && pending.current !== null) {
      const ms = pending.current;
      pending.current = null;
      try {
        await profileApi.updateWatchProgress(movieId, {
          edition_id: editionId,
          state: ms === 0 ? 'NOT_STARTED' : ms >= duration ? 'COMPLETED' : 'IN_PROGRESS',
          progress_ms: ms,
          completed_reveal_ids: ms === 0 ? [] : reveals.filter(r => ms >= Math.max(r.timestampMs, r.spoilerCutoffMs)).map(r => r.revealId),
        });
        if (latest.current === ms && pending.current === null) {
          if (mounted.current) setFailed(false);
          // A replaced control may still finish its request. Re-fetch the
          // active viewer's server progress; never apply the old response.
          callbacks.current.onProgressChange();
        }
      } catch {
        if (mounted.current && latest.current === ms && pending.current === null) {
          setFailed(true);
        }
      }
    }
    saving.current = false;
    if (mounted.current) callbacks.current.onSavingChange?.(false);
  };

  const changeProgress = (value: number) => {
    const ms = clamp(value);
    latest.current = ms;
    pending.current = ms;
    setSelectedProgress(ms);
    setFailed(false);
    callbacks.current.onSavingChange?.(true);
    onProgressPreview?.(ms);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), 300);
  };

  const time = (ms: number) => {
    const formatted = formatTimestampMs(ms);
    return formatted.length >= 2 ? formatted.slice(1, -1) : '00:00:00';
  };

  if (!duration) {
    return (
      <section
        className="film-journey-controls watch-timeline disabled-timeline"
        data-testid="film-journey-controls"
        aria-label="Film exploration and watch progress controls"
      >
        <div className="watch-timeline-heading">
          <div>
            <h2>Viewing progress</h2>
            <p>Viewing progress timeline is unavailable because runtime or edition metadata is missing for this film.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      className="film-journey-controls watch-timeline"
      data-testid="film-journey-controls"
      aria-label="Film exploration and watch progress controls"
    >
      <label htmlFor="watch-progress-timeline" className="watch-timeline-label">
        Your viewing position <output>{time(selectedProgress)} / {time(duration)}</output>
      </label>
      {children}
      <input
        id="watch-progress-timeline"
        data-testid="film-timeline-slider"
        aria-label="Viewing progress timeline"
        aria-valuetext={`${time(selectedProgress)} of ${time(duration)}`}
        type="range"
        min={0}
        max={duration}
        step="any"
        value={selectedProgress}
        disabled={!duration}
        style={{ '--watch-progress': `${duration ? (selectedProgress / duration) * 100 : 0}%` } as React.CSSProperties}
        onChange={e => {
          const raw = Number(e.target.value);
          const val = Math.round(raw);
          changeProgress(val);
        }}
        onKeyDown={e => {
          if (e.key === 'Home') {
            e.preventDefault();
            changeProgress(0);
            void flush();
          } else if (e.key === 'End') {
            e.preventDefault();
            changeProgress(duration);
            void flush();
          }
        }}
        onPointerUp={() => void flush()}
        onKeyUp={() => void flush()}
        onBlur={() => void flush()}
      />
      <div className="watch-timeline-ticks" aria-hidden="true">
        <span>{time(0)}</span>
        <span>{time(duration / 2)}</span>
        <span>{time(duration)}</span>
      </div>
      {failed && (
        <p className="watch-save-status" role="alert">
          Could not save this position.{' '}
          <button
            type="button"
            onClick={() => {
              pending.current = selectedProgress;
              void flush();
            }}
          >
            Retry
          </button>
        </p>
      )}
    </section>
  );
}
