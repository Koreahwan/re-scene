export function supportsSelectedPortion(movie: string, edition: string): boolean {
  return [
    'the-bat-whispers-1930:tbw-fullscreen-archive',
    'the-greene-murder-case-1929:gmc-archive-1929',
    'the-thirteenth-chair-1929:ttc-archive-1929',
  ].includes(`${movie}:${edition}`);
}

export interface PortionSegment {
  segment_id: string;
  start_ms: number;
  end_ms: number;
  available_after_ms: number;
  summary: string;
  reading: string;
  source_method: 'SAMPLED_STILLS_ONLY' | 'AUDIO_AND_SAMPLED_STILLS';
  observations: { timestamp_ms: number; evidence_end_ms: number; text: string; uncertainty: string }[];
}

export interface SelectedPortion {
  work_id: string;
  edition_id: string;
  selected_progress_ms: number;
  covered_until_ms: number;
  mode: 'SELECTED_PORTION';
  human_review_status: 'NOT_REVIEWED';
  model_id: string;
  segments: PortionSegment[];
}

export function validateSelectedPortion(data: SelectedPortion, movie: string, edition: string, position: number): SelectedPortion {
  const time = (v: number) => Number.isSafeInteger(v) && v >= 0;
  if (data?.work_id !== movie || data.edition_id !== edition || data.mode !== 'SELECTED_PORTION' ||
      !time(data.selected_progress_ms) || data.selected_progress_ms > position ||
      !time(data.covered_until_ms) || data.covered_until_ms > data.selected_progress_ms || !Array.isArray(data.segments)) {
    throw new Error('The selected-portion response did not match this viewing position.');
  }
  for (const segment of data.segments) {
    if (![segment.start_ms, segment.end_ms, segment.available_after_ms].every(time) ||
        segment.start_ms >= segment.end_ms || segment.end_ms > segment.available_after_ms ||
        segment.available_after_ms > data.selected_progress_ms ||
        typeof segment.summary !== 'string' || typeof segment.reading !== 'string' || !Array.isArray(segment.observations) ||
        segment.observations.some(o => !time(o.timestamp_ms) || !time(o.evidence_end_ms) ||
          o.timestamp_ms < segment.start_ms || o.timestamp_ms > segment.end_ms ||
          o.evidence_end_ms < segment.start_ms || o.evidence_end_ms > segment.end_ms || typeof o.text !== 'string')) {
      throw new Error('A segment exceeded the selected viewing position.');
    }
  }
  return data;
}
