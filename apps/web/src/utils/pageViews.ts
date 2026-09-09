const pending = new Set<string>();
const memory = new Map<string, { event: string; at: number; sent?: boolean }>();

/** One view per content per tab per 30 minutes; retries reuse the event ID. */
export async function recordPageView(kind: 'films' | 'magazine', id: string) {
  if (import.meta.env.VITE_VISUAL_FIXTURE_MODE === 'true') return;
  const key = `reframe:view:${kind}:${id}`;
  if (pending.has(key)) return;
  pending.add(key);
  try {
    let previous = memory.get(key);
    try { previous = JSON.parse(sessionStorage.getItem(key) || 'null') || previous; } catch { /* Storage unavailable. */ }
    const fresh = previous && Date.now() - previous.at >= 0 && Date.now() - previous.at < 30 * 60 * 1000;
    if (fresh && previous?.sent) return;
    const event = fresh && previous ? previous : { event: crypto.randomUUID(), at: Date.now(), sent: false };
    const save = () => {
      memory.set(key, event);
      try { sessionStorage.setItem(key, JSON.stringify(event)); } catch { /* Retain in memory. */ }
    };
    save();
    const response = await fetch(`/api/v1/${kind}/${encodeURIComponent(id)}/views`, {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_id: event.event }),
    });
    if (response.ok) { event.sent = true; save(); }
  } catch { /* Analytics must never prevent reading. */ }
  finally { pending.delete(key); }
}
