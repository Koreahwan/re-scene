import React, { useEffect, useRef, useState } from 'react';
import './CommentSpoiler.css';

export function CommentSpoiler({ canReveal, pending = false, inspectionStatus, onReveal }: {
  canReveal: boolean; pending?: boolean; inspectionStatus?: string; onReveal: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const showButton = useRef<HTMLButtonElement>(null);
  const wasConfirming = useRef(false);
  useEffect(() => {
    if (wasConfirming.current && !confirming) showButton.current?.focus();
    wasConfirming.current = confirming;
  }, [confirming]);
  const checked = ['VERIFIED', 'AI_CLEAR', 'AI_SPOILER'].includes(inspectionStatus || '');
  return <div className="comment-spoiler-gate">
    {/* Decorative bars only: the server does not send the hidden comment body. */}
    <div className="comment-spoiler-blur" aria-hidden="true"><i /><i /><i /></div>
    <div className="comment-spoiler-warning">
      <strong>Possible spoilers</strong>
      <span>{checked ? 'Open only if you are ready for story details.' : 'Spoiler check incomplete. Open at your own risk.'}</span>
      {confirming ? <div className="comment-spoiler-confirm" role="group" aria-label="Confirm spoiler reveal">
        <span>This may reveal plot details or the ending. Open this comment?</span>
        <div><button type="button" autoFocus disabled={pending} onClick={() => setConfirming(false)}>Cancel</button>
          <button type="button" disabled={pending || !canReveal} onClick={() => { setConfirming(false); onReveal(); }}>Yes, show comment</button></div>
      </div> : <button ref={showButton} type="button" disabled={pending || !canReveal} onClick={() => setConfirming(true)}>
        {pending ? 'Opening…' : canReveal ? 'Show comment' : 'Comment unavailable'}
      </button>}
    </div>
  </div>;
}
