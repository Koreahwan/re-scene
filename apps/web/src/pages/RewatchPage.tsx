import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/apiClient';
import { ProofCardDTO } from '../types/api';
import { AppButton } from '../components/AppButton';

interface RewatchPageProps {
  journeyId?: string;
  revealId?: string;
  workId?: string;
  navigate: (path: string) => void;
}

export const RewatchPage: React.FC<RewatchPageProps> = ({
  revealId: propRevealId,
  workId: propWorkId,
  navigate
}) => {
  const [scenes, setScenes] = useState<Array<{scene_id: string; start_ms: number; end_ms: number}>>([]);
  const [revealVisible, setRevealVisible] = useState(false);
  const [selectedTimestampMs, setSelectedTimestampMs] = useState(0);

  const queryParams = new URLSearchParams(window.location.search);
  const rawWorkId = propWorkId || queryParams.get('work_id') || queryParams.get('workId') || queryParams.get('movieId') || 'the-bat-whispers-1930';
  const workId = rawWorkId.trim();
  const revealId = queryParams.get('reveal_id') || queryParams.get('revealId') || propRevealId
    || (workId === 'the-bat-whispers-1930' ? 'reveal-anderson-identity' : '');
  const rawEditionId = queryParams.get('edition_id') || queryParams.get('editionId');
  const [edition, setEdition] = useState<{ workId: string; editionId: string } | null>(null);
  const [metadataLoading, setMetadataLoading] = useState(true);
  const isWorkSupported = edition?.workId === workId;
  const isEditionValid = isWorkSupported && (!rawEditionId || rawEditionId === edition?.editionId);
  useEffect(() => {
    let active = true;
    setMetadataLoading(true);
    setEdition(null);
    apiClient.catalog.getFilmDetail(workId, rawEditionId || undefined)
      .then(({ data }) => {
        if (active && data.movie_id === workId && data.edition_id) {
          setEdition({ workId, editionId: data.edition_id });
        }
      })
      .catch(() => { if (active) setEdition(null); })
      .finally(() => { if (active) setMetadataLoading(false); });
    return () => { active = false; };
  }, [workId, rawEditionId]);

  const initialSceneId = queryParams.get('scene_id') || queryParams.get('sceneId');
  const rawProofId = queryParams.get('proof_id') || queryParams.get('proofId');
  const rawTimestamp = queryParams.get('timestamp');
  const rawTime = queryParams.get('time');

  const [invalidSceneError, setInvalidSceneError] = useState<string | null>(null);
  const [invalidProofError, setInvalidProofError] = useState<string | null>(null);
  const [invalidRevealError, setInvalidRevealError] = useState<string | null>(null);

  const isInvalidTimeParam = (() => {
    if (rawTimestamp != null) {
      const ms = Number(rawTimestamp);
      if (!Number.isFinite(ms) || ms < 0) return true;
    }
    if (rawTime != null) {
      const s = Number(rawTime);
      if (!Number.isFinite(s) || s < 0) return true;
    }
    return false;
  })();

  // Strict contract:
  // timestamp is explicitly in milliseconds (e.g. timestamp=5000 -> 5.0 seconds).
  // time is explicitly in seconds (e.g. time=5 -> 5.0 seconds).
  // Negative or NaN values are rejected.
  const parsedTargetSec = (() => {
    if (rawTimestamp != null) {
      const ms = Number(rawTimestamp);
      if (Number.isFinite(ms) && ms >= 0) {
        return ms / 1000;
      }
      return null;
    }
    if (rawTime != null) {
      const s = Number(rawTime);
      if (Number.isFinite(s) && s >= 0) {
        return s;
      }
      return null;
    }
    return null;
  })();

  useEffect(() => {
    const scene = scenes.find(s => s.scene_id === initialSceneId);
    setSelectedTimestampMs(parsedTargetSec != null ? parsedTargetSec * 1000 : scene?.start_ms || 0);
  }, [scenes, initialSceneId, parsedTargetSec, workId]);

  useEffect(() => {
    if (!isWorkSupported) return;
    setScenes([]);
    setRevealVisible(false);
    setInvalidSceneError(null);
    setInvalidRevealError(null);
    let active = true;

    apiClient.catalog.getSceneIndex(workId, edition?.editionId)
      .then(res => {
        if (!active) return;
        const loadedScenes = res.data || [];
        setScenes(loadedScenes);
        if (initialSceneId) {
          const match = loadedScenes.find(s => s.scene_id === initialSceneId);
          if (match) {
            setInvalidSceneError(null);
          } else if (loadedScenes.length > 0) {
            setInvalidSceneError(`Scene "${initialSceneId}" does not belong to this film.`);
          }
        }
      })
      .catch(() => { if (active) setInvalidSceneError('Could not load scene information.'); });

    apiClient.catalog.getReveals(workId, edition?.editionId)
      .then(res => {
        if (!active) return;
        const revealsList = res.data || [];
        const matchingReveal = revealsList.find(r => r.reveal_id === revealId);
        if (!revealId) {
          setInvalidRevealError(null);
        } else if (!matchingReveal) {
          setInvalidRevealError(`Reveal "${revealId}" does not belong to this film.`);
        } else {
          setInvalidRevealError(null);
          setRevealVisible(matchingReveal.visibility === 'VISIBLE');
        }
      })
      .catch(() => {
        if (active) setInvalidRevealError('Could not load reveal information.');
      });

    return () => { active = false; };
  }, [revealId, isWorkSupported, initialSceneId, workId, edition?.editionId]);

  const [proofs, setProofs] = useState<ProofCardDTO[]>([]);
  const [selectedProofIndex, setSelectedProofIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!isWorkSupported || !revealId) {
      setProofs([]);
      setIsLoading(false);
      return;
    }
    let isMounted = true;
    setIsLoading(true);
    setErrorMsg(null);
    setInvalidProofError(null);

    apiClient.proof
      .getProofsForReveal(revealId)
      .then((res) => {
        if (isMounted) {
          const list = (res.data || []).filter(p => p.work_id === workId && p.edition_id === edition?.editionId);
          setProofs(list);
          if (rawProofId) {
            const idx = list.findIndex(p => p.proof_id === rawProofId);
            if (idx >= 0) {
              setSelectedProofIndex(idx);
              setInvalidProofError(null);
            } else {
              setInvalidProofError(`Evidence "${rawProofId}" does not belong to this reveal.`);
            }
          } else {
            setSelectedProofIndex(0);
            setInvalidProofError(null);
          }
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setErrorMsg(err.message || 'Could not load interpretation evidence.');
          setProofs([]);
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [revealId, isWorkSupported, rawProofId, workId, edition?.editionId]);

  const activeProof = proofs.length > 0 ? proofs[selectedProofIndex] : null;
  const isVerifiedCanon = activeProof?.verification_status === 'VERIFIED_CANON';

  const hasValidationError = (
    !isWorkSupported
    || !isEditionValid
    || isInvalidTimeParam
    || invalidSceneError != null
    || invalidProofError != null
    || invalidRevealError != null
    || errorMsg != null
  );

  if (metadataLoading) return <div className="page-container" role="status">Loading film edition…</div>;

  if (hasValidationError) {
    const errorTitle = !isWorkSupported
      ? 'Film unavailable'
      : !isEditionValid
      ? 'Edition unavailable'
      : isInvalidTimeParam
      ? 'Invalid scene timestamp'
      : invalidSceneError != null
      ? 'Invalid scene'
      : invalidProofError != null
      ? 'Invalid evidence'
      : invalidRevealError != null
      ? 'Invalid reveal'
      : 'Could not load narrative data';

    const errorDesc = !isWorkSupported
      ? `Information for film or edition "${workId}" is unavailable.`
      : !isEditionValid
      ? `Edition "${rawEditionId}" does not belong to this film.`
      : isInvalidTimeParam
      ? 'The scene timestamp must be a non-negative number.'
      : invalidSceneError || invalidProofError || invalidRevealError || errorMsg || 'The requested data was not found.';

    return (
      <div className="page-container" data-testid="rewatch-unsupported-work">
        <div className="page-content" style={{ maxWidth: '1080px', gap: '28px' }}>
          <button
            onClick={() => navigate('/films')}
            style={{
              background: 'none',
              border: 'none',
              color: '#888888',
              fontSize: '14px',
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            ← Back to Movies
          </button>
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #FFD0D0',
              borderRadius: '12px',
              padding: '48px 32px',
              textAlign: 'center'
            }}
          >
            <h2 style={{ fontSize: '20px', color: '#D32F2F', margin: '0 0 12px 0' }}>
              {errorTitle}
            </h2>
            <p style={{ color: '#6B6B75', fontSize: '14px', maxWidth: '540px', margin: '0 auto 24px auto', lineHeight: 1.6 }}>
              {errorDesc}
            </p>
            <AppButton
              variant="primary"
              size="md"
              onClick={() => navigate(`/films/${encodeURIComponent(workId)}`)}
            >
              Open Film
            </AppButton>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-content" style={{ maxWidth: '1080px', gap: '28px' }}>
        <button
          onClick={() => navigate(`/films/${encodeURIComponent(workId)}`)}
          style={{
            background: 'none',
            border: 'none',
            color: '#888888',
            fontSize: '14px',
            cursor: 'pointer',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          ← Back to Film
        </button>

        {/* Header */}
        <div
          style={{
            background: '#FFFFFF',
            border: '1px solid #EEEEEE',
            borderRadius: '12px',
            padding: '32px',
            boxShadow: '0 2px 8px #00000008'
          }}
        >
          <div
            style={{
              display: 'inline-block',
              background: '#F0EDFF',
              color: '#4C22F4',
              padding: '4px 10px',
              borderRadius: '9999px',
              fontSize: '12px',
              fontWeight: 700,
              marginBottom: '10px'
            }}
          >
            RE:FRAME SCENE ANALYSIS
          </div>
          <h1 style={{ fontSize: '26px', fontWeight: 700, color: '#2D2D34', margin: '0 0 8px 0' }}>
            Compare scene interpretations
          </h1>
          <p style={{ color: '#888888', fontSize: '14px', margin: 0 }}>
            Compare available perspectives and evidence from the same scene.
          </p>
        </div>

        <section aria-label="Scene references" data-testid="scene-analysis-references">
          <p style={{ fontSize: 13, color: '#6B6B75' }}>Video playback is not provided on this site. Scene references follow your saved viewing progress.</p>
          <p>Selected scene timestamp: <output data-testid="selected-scene-timestamp">{(selectedTimestampMs / 1000).toFixed(2)}s</output></p>
          {scenes.length > 0 && <div className="journey-actions">
            <label>Scene reference <select aria-label="Scene reference" value={scenes.some(s => s.start_ms === selectedTimestampMs) ? selectedTimestampMs : ''} onChange={e => setSelectedTimestampMs(Number(e.target.value))}>
              <option value="" disabled>Choose a scene</option>
              {scenes.map(s => <option key={s.scene_id} value={s.start_ms}>{s.scene_id} · {Math.floor(s.start_ms / 60000)}m {Math.floor(s.start_ms / 1000) % 60}s</option>)}
            </select></label>
            {revealVisible && <button onClick={() => navigate(`/theory-lab?reveal_id=${encodeURIComponent(revealId)}`)}>Write a theory about this reveal</button>}
          </div>}
        </section>

        {isLoading ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#888888' }}>
            Loading narrative evidence...
          </div>
        ) : errorMsg ? (
          <div
            style={{
              padding: '24px',
              background: '#FFEBEE',
              border: '1px solid #EB5757',
              borderRadius: '8px',
              color: '#EB5757',
              fontSize: '14px'
            }}
          >
            {errorMsg}
          </div>
        ) : !activeProof || proofs.length === 0 ? (
          <div
            data-testid="rewatch-empty-analysis"
            style={{
              background: '#FFFFFF',
              border: '1px solid #EEEEEE',
              borderRadius: '12px',
              padding: '48px 32px',
              textAlign: 'center'
            }}
          >
            <h2 style={{ fontSize: '18px', color: '#2D2D34', margin: '0 0 10px 0' }}>
              Interpretations for this reveal are not yet available
            </h2>
            <p style={{ color: '#888888', fontSize: '14px', maxWidth: '540px', margin: '0 auto 24px auto', lineHeight: 1.6 }}>
              Return to the film to explore available analysis. Test output is not presented as verified interpretation.
            </p>
            <AppButton
              variant="primary"
              onClick={() => navigate(`/films/${encodeURIComponent(workId)}?edition_id=${encodeURIComponent(edition?.editionId || '')}`)}
            >
              Back to Film
            </AppButton>
          </div>
        ) : (
          <div>
            {proofs.length > 1 && (
              <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', overflowX: 'auto', paddingBottom: '4px' }}>
                {proofs.map((p, idx) => (
                  <button
                    key={p.proof_id || idx}
                    onClick={() => setSelectedProofIndex(idx)}
                    style={{
                      background: selectedProofIndex === idx ? '#4C22F4' : '#FFFFFF',
                      border: selectedProofIndex === idx ? '1px solid #4C22F4' : '1px solid #EEEEEE',
                      color: selectedProofIndex === idx ? '#FFFFFF' : '#555555',
                      padding: '8px 16px',
                      borderRadius: '8px',
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    {p.title || `Scene ${idx + 1}`}
                  </button>
                ))}
              </div>
            )}

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(min(340px, 100%), 1fr))',
                gap: '24px',
                marginBottom: '32px'
              }}
            >
              {/* Perspective A: First-Time Viewer */}
              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #EEEEEE',
                  borderRadius: '12px',
                  padding: '24px',
                  boxShadow: '0 2px 8px #00000008'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#888888' }}>
                    Perspective A: First viewing
                  </span>
                  <span style={{ fontSize: '11px', background: '#F5F5F5', color: '#888888', padding: '2px 8px', borderRadius: '4px' }}>
                    BLIND
                  </span>
                </div>
                <p style={{ color: '#555555', fontSize: '14px', lineHeight: 1.6, margin: 0 }}>
                  {activeProof.blind_explanation || 'No first-viewing interpretation is available.'}
                </p>
              </div>

              {/* Perspective B: Reframed Truth */}
              <div
                style={{
                  background: '#F0EDFF',
                  border: '1px solid #4C22F440',
                  borderRadius: '12px',
                  padding: '24px',
                  boxShadow: '0 2px 8px #00000008'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#4C22F4' }}>
                    Perspective B: After the reveal
                  </span>
                  <span style={{ fontSize: '11px', background: '#4C22F4', color: '#FFFFFF', padding: '2px 8px', borderRadius: '4px' }}>
                    {isVerifiedCanon ? 'VERIFIED CANON' : 'Unverified interpretation'}
                  </span>
                </div>
                <p style={{ color: '#2D2D34', fontSize: '14px', lineHeight: 1.6, margin: 0 }}>
                  {activeProof.reveal_explanation || 'No post-reveal explanation is available.'}
                </p>
              </div>
            </div>

            {/* Evidence Chain */}
            {activeProof.observed_premises && activeProof.observed_premises.length > 0 && (
              <div
                style={{
                  background: '#FFFFFF',
                  border: '1px solid #EEEEEE',
                  borderRadius: '12px',
                  padding: '24px',
                  boxShadow: '0 2px 8px #00000008'
                }}
              >
                <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#2D2D34', margin: '0 0 16px 0' }}>
                  Scene evidence
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activeProof.observed_premises.map((prem, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: '#F8F9FA',
                        border: '1px solid #EEEEEE',
                        borderRadius: '8px',
                        padding: '12px 16px',
                        fontSize: '14px',
                        color: '#2D2D34'
                      }}
                    >
                      {prem.fact || prem.display_fact || prem.action || (prem.actor ? `${prem.actor} in ${prem.scene_id}` : prem.scene_id)}
                      <button onClick={() => setSelectedTimestampMs(prem.timestamp_ms)} style={{ marginLeft: 12 }}>Inspect scene timestamp</button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
