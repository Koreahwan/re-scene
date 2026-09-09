import React from 'react';
import { ProofCardDTO } from '../types/api';

export interface ProofCardProps {
  proof: ProofCardDTO;
  onSelect?: (proofId: string) => void;
  variant?: 'verified' | 'engine_inference' | 'abstained';
  state?: 'locked' | 'visible' | 'masked';
}

export const ProofCard: React.FC<ProofCardProps> = ({ proof, onSelect }) => {
  const ptype = proof.proof_type?.replace(/_/g, ' ') || 'VERIFIED CLUE';
  const isNormative = ['KNOWLEDGE_LEAK', 'CLAIM_ACTION_CONFLICT', 'HIDDEN_PLAN_CHAIN'].includes(proof.proof_type);

  return (
    <article
      className="proof-card"
      data-testid={`proof-card-${proof.proof_id}`}
      onClick={() => onSelect && onSelect(proof.proof_id)}
      style={{
        background: '#161B22E6',
        border: '1px solid #30363DCC',
        borderRadius: '10px',
        padding: '24px',
        margin: '16px 0',
        cursor: onSelect ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        boxShadow: '0 4px 12px #00000033'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{
            background: isNormative ? '#388BFD26' : '#D2992226',
            color: isNormative ? '#58a6ff' : '#d29922',
            border: `1px solid ${isNormative ? '#388BFD66' : '#D2992266'}`,
            padding: '3px 10px',
            borderRadius: '12px',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.5px'
          }}>
            {ptype}
          </span>
          <span style={{
            background: '#6E768126',
            color: '#8b949e',
            border: '1px solid #6E76814C',
            padding: '3px 8px',
            borderRadius: '12px',
            fontSize: '11px'
          }}>
            {proof.trust_label || 'Engine-supported interpretation'}
          </span>
        </div>
        {proof.proof_badge && (
          <span style={{
            background: '#23863626',
            color: '#3fb950',
            border: '1px solid #23863666',
            padding: '3px 10px',
            borderRadius: '12px',
            fontSize: '11px',
            fontWeight: 600
          }}>
            {proof.proof_badge}
          </span>
        )}
      </div>

      <h3 style={{ margin: '0 0 16px 0', fontSize: '18px', color: '#f0f6fc', lineHeight: 1.4 }}>
        {proof.title}
      </h3>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '14px',
        marginBottom: '18px'
      }}>
        <div style={{
          background: '#0D111799',
          border: '1px solid #30363D99',
          borderRadius: '8px',
          padding: '14px'
        }}>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '12px', textTransform: 'uppercase', color: '#8b949e', letterSpacing: '0.5px' }}>
            Before Reveal (Blind Audience View)
          </h4>
          <p style={{ margin: 0, fontSize: '14px', color: '#c9d1d9', lineHeight: 1.5 }}>
            {proof.blind_explanation}
          </p>
        </div>

        <div style={{
          background: '#1F6FEB14',
          border: '1px solid #388BFD4C',
          borderRadius: '8px',
          padding: '14px'
        }}>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '12px', textTransform: 'uppercase', color: '#58a6ff', letterSpacing: '0.5px' }}>
            After Reveal (Reframed Narrative Reality)
          </h4>
          <p style={{ margin: 0, fontSize: '14px', color: '#f0f6fc', lineHeight: 1.5 }}>
            {proof.reveal_explanation}
          </p>
        </div>
      </div>

      {proof.observed_premises && proof.observed_premises.length > 0 && (
        <div style={{ marginBottom: '18px' }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: '12px', textTransform: 'uppercase', color: '#8b949e', letterSpacing: '0.5px' }}>
            Verified Forensic Premises ({proof.observed_premises.length})
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {proof.observed_premises.map((prem, idx) => (
              <div
                key={prem.event_id || prem.fact_id || idx}
                style={{
                  background: '#0D111766',
                  border: '1px solid #30363D66',
                  borderRadius: '6px',
                  padding: '10px 14px',
                  fontSize: '13px'
                }}
              >
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 600, color: '#58a6ff' }}>{prem.event_id || prem.fact_id || `Premise ${idx + 1}`}</span>
                  <span style={{ color: '#8b949e' }}>Scene {prem.scene_id}</span>
                  <span style={{ color: '#8b949e' }}>{(prem.timestamp_ms / 1000).toFixed(1)}s</span>
                </div>
                <p style={{ margin: '0 0 4px 0', color: '#c9d1d9' }}>{prem.fact || prem.display_fact || prem.action}</p>
                {prem.canonical_content_hash && (
                  <span style={{ fontSize: '11px', color: '#6e7681', fontFamily: 'monospace' }}>
                    SHA-256: {prem.canonical_content_hash.slice(0, 16)}...
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderTop: '1px solid #30363D99',
        paddingTop: '14px',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
          <div>
            <span style={{ color: '#8b949e' }}>Proof Strength: </span>
            <strong style={{ color: '#58a6ff' }}>{((proof.proof_strength || 0) * 100).toFixed(0)}%</strong>
          </div>
          <div>
            <span style={{ color: '#8b949e' }}>Fan Salience: </span>
            <strong style={{ color: '#d29922' }}>{((proof.fan_impact || 0) * 100).toFixed(0)}%</strong>
          </div>
          {(proof.counterfactual_results?.wrong_reveal_delta !== undefined || proof.counterfactual_robustness?.reveal_swap_delta !== undefined) && (
            <div>
              <span style={{ color: '#8b949e' }}>Control Delta: </span>
              <strong style={{ color: '#3fb950' }}>
                {(proof.counterfactual_results?.wrong_reveal_delta ?? proof.counterfactual_robustness?.reveal_swap_delta)?.toFixed(2)}
              </strong>
            </div>
          )}
        </div>
        {onSelect && (
          <span style={{ color: '#58a6ff', fontSize: '13px', fontWeight: 600 }}>
            Inspect Evidence Chain →
          </span>
        )}
      </div>
    </article>
  );
};
