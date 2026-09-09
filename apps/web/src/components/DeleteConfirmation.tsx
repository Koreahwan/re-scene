import React, { useRef, useState } from 'react';
import { AppModal } from './AppModal';

/** Keep destructive confirmation and any failure inside the site, with Cancel focused first. */
export function DeleteConfirmation({ kind, detail, onCancel, onDelete }: {
  kind: string; detail?: string; onCancel: () => void; onDelete: () => Promise<void>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const busy = useRef(false);
  const confirm = async () => {
    if (busy.current) return;
    busy.current = true; setPending(true); setError('');
    try { await onDelete(); onCancel(); }
    catch (err) { setError(err instanceof Error ? err.message : `Unable to delete ${kind}. Please try again.`); }
    finally { busy.current = false; setPending(false); }
  };
  return <AppModal isOpen title={`Delete this ${kind}?`} size="sm" showCloseButton={false} dialogStyle={{ padding: 24, width: 'calc(100vw - 32px)', boxSizing: 'border-box' }} onClose={() => { if (!busy.current) onCancel(); }}>
    <p>{detail || 'This action cannot be undone.'}</p>
    {error && <p role="alert">{error}</p>}
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
      <button type="button" disabled={pending} onClick={onCancel} style={{ padding: '10px 18px', border: '1px solid #D5D5DB', borderRadius: 8, background: '#fff', cursor: 'pointer' }}>Cancel</button>
      <button type="button" disabled={pending} onClick={() => void confirm()} style={{ padding: '10px 18px', border: 0, borderRadius: 8, background: '#4C22F4', color: '#fff', cursor: 'pointer' }}>{pending ? 'Deleting…' : 'Delete'}</button>
    </div>
  </AppModal>;
}
