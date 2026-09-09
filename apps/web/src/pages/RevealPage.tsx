import React, { useEffect, useState } from 'react';
import { RevealDTO, ProofCardDTO } from '../types/api';
import { apiClient } from '../services/apiClient';
import { ProofCard } from '../components/ProofCard';
import { SpoilerGate } from '../components/SpoilerGate';
import { LoadingState, ErrorState, EmptyState } from '../components/FeedbackStates';

interface RevealPageProps {
  movieId?: string;
  revealId: string;
  navigate: (path: string) => void;
}

export const RevealPage: React.FC<RevealPageProps> = ({
  movieId = 'the-bat-whispers-1930',
  revealId,
  navigate
}) => {
  const [reveal, setReveal] = useState<RevealDTO | null>(null);
  const [proofs, setProofs] = useState<ProofCardDTO[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRevealAndProofs();
  }, [revealId]);

  const loadRevealAndProofs = async () => {
    try {
      setLoading(true);
      setError(null);
      const [revRes, proofsRes] = await Promise.all([
        apiClient.catalog.getRevealDetail(revealId),
        apiClient.proof.getProofsForReveal(revealId)
      ]);
      setReveal(revRes.data);
      setProofs(proofsRes.data || []);
    } catch (err: any) {
      setError(err.message || 'Could not load reveal clues.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <LoadingState message="Loading reveal clues..." />;
  if (error) return <ErrorState message={error} onRetry={loadRevealAndProofs} />;
  if (!reveal) return <EmptyState title="Reveal not found" message={`No reveal was found for '${revealId}'.`} />;

  return (
    <div className="page-container">
      <div className="page-content" style={{ maxWidth: '1080px', gap: '28px' }}>
        {/* Back button */}
        <button
          onClick={() => navigate(`/films/${movieId}`)}
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

        {/* Reveal Header with Spoiler Gate */}
        <SpoilerGate
          visibility={reveal.visibility}
          safeTitle={reveal.safe_title}
          safePreview={reveal.safe_preview?.summary || 'This reveal contains spoilers.'}
        >
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #EEEEEE',
              borderRadius: '12px',
              padding: '32px',
              boxShadow: '0 2px 8px #00000008'
            }}
          >
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '12px' }}>
              <span
                style={{
                  background: '#F0EDFF',
                  color: '#4C22F4',
                  padding: '4px 10px',
                  borderRadius: '9999px',
                  fontSize: '12px',
                  fontWeight: 700
                }}
              >
                Spoiler cutoff: {(reveal.timestamp_ms / 60000).toFixed(1)} minutes
              </span>
              <span style={{ fontSize: '13px', color: '#888888' }}>
                Subject: {reveal.character_or_subject || 'Narrative clue'}
              </span>
            </div>

            <h1 style={{ margin: '0 0 16px 0', fontSize: '26px', fontWeight: 700, color: '#2D2D34' }}>
              {reveal.title}
            </h1>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '16px',
                background: '#F8F9FA',
                border: '1px solid #EEEEEE',
                borderRadius: '8px',
                padding: '16px'
              }}
            >
              <div>
                <div style={{ fontSize: '12px', color: '#888888', textTransform: 'uppercase', marginBottom: '4px' }}>
                  Before the reveal
                </div>
                <div style={{ fontSize: '14px', color: '#555555' }}>
                  {reveal.previous_belief || 'No first-viewing interpretation is available.'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#4C22F4', textTransform: 'uppercase', marginBottom: '4px' }}>
                  After the reveal
                </div>
                <div style={{ fontSize: '14px', color: '#2D2D34', fontWeight: 600 }}>
                  {reveal.revealed_fact || 'No post-reveal explanation is available.'}
                </div>
              </div>
            </div>
          </div>
        </SpoilerGate>

        {/* Proofs Section */}
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <div>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#2D2D34', margin: '0 0 4px 0' }}>
                Narrative clues ({proofs.length})
              </h2>
              <p style={{ margin: 0, fontSize: '13px', color: '#888888' }}>
                {((reveal?.timestamp_ms || 4860000) / 60000).toFixed(1)} minutes from earlier scenes.
              </p>
            </div>
            <button
              onClick={() => navigate(`/theory-lab?reveal_id=${revealId}`)}
              style={{
                background: '#F0EDFF',
                border: '1px solid #4C22F4',
                color: '#4C22F4',
                padding: '8px 16px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              + Propose a theory
            </button>
          </div>

          {proofs.length === 0 ? (
            <EmptyState
              title="No clues available"
              message="There are no published clues for this reveal yet."
            />
          ) : (
            <div>
              {proofs.map((proof) => (
                <ProofCard
                  key={proof.proof_id}
                  proof={proof}
                  onSelect={(pId) => navigate(`/proofs/${pId}`)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
