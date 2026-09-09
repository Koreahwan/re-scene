export interface ReviewDraft {
  owner: string | null;
  rating: number;
  text: string;
  containsSpoilers: boolean;
  editing: { id: string; version_no: number } | null;
  requestKey: string;
  savedAt: number;
}
const prefix = 'rescene.review-draft.';
export function saveReviewDraft(movieId: string, draft: ReviewDraft): void {
  try { sessionStorage.setItem(prefix + movieId, JSON.stringify(draft)); } catch { /* The in-page draft remains available. */ }
}
export function takeReviewDraft(movieId: string, owner: string | null): ReviewDraft | null {
  try {
    const raw = sessionStorage.getItem(prefix + movieId);
    if (!raw) return null;
    const value = JSON.parse(raw);
    sessionStorage.removeItem(prefix + movieId);
    if (value.owner !== null && value.owner !== owner) return null;
    if (typeof value.text !== 'string' || value.text.length > 10000 ||
        !Number.isInteger(value.rating) || value.rating < 0 || value.rating > 5 ||
        typeof value.requestKey !== 'string' || Date.now() - value.savedAt > 3600000) return null;
    return value;
  } catch { return null; }
}
export function clearReviewDrafts(): void {
  try {
    Object.keys(sessionStorage).filter(key => key.startsWith(prefix) || key.startsWith('rescene:comment-draft:')).forEach(key => sessionStorage.removeItem(key));
  } catch { /* Storage may be disabled. */ }
}
