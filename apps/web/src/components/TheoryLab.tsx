import React, { useState } from 'react';
import { apiClient } from '../services/apiClient';
import { TheoryValidationResultDTO } from '../types/api';

interface TheoryLabProps {
  targetRevealId: string;
}

export const TheoryLab: React.FC<TheoryLabProps> = ({ targetRevealId }) => {
  const [title, setTitle] = useState('');
  const [explanation, setExplanation] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<TheoryValidationResultDTO | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);
    setResult(null);

    try {
      // 1. Create Theory Draft (v1)
      const draftRes = await apiClient.createTheoryDraft(title, explanation, targetRevealId);
      const theoryId = draftRes.data.theory_id;

      // 2. Submit Validation Run
      const runRes = await apiClient.submitTheoryValidationRun(theoryId, targetRevealId);
      const newRunId = runRes.data.run_id;

      // 3. Poll for result
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const checkRes = await apiClient.getTheoryValidationResult(newRunId);
        if (checkRes.data && checkRes.data.validation_verdict) {
          setResult(checkRes.data);
          break;
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to submit theory validation');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="theory-lab-section" data-testid="theory-lab">
      <h2>Fan Theory Lab</h2>
      <p className="section-subtitle">
        Propose an alternative hypothesis and test its semantic grounding against pre-reveal canon facts.
      </p>

      <form onSubmit={handleSubmit} className="theory-form">
        <div className="form-group">
          <label htmlFor="theory-title">Theory Title</label>
          <input
            id="theory-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Fireplace Wall Mechanical Lever Connection"
            required
            minLength={3}
          />
        </div>

        <div className="form-group">
          <label htmlFor="theory-explanation">Premise Explanation</label>
          <textarea
            id="theory-explanation"
            rows={4}
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            placeholder="Detail your observations of characters, objects, or actions before the reveal..."
            required
            minLength={10}
          />
        </div>

        <button type="submit" className="btn-primary" disabled={isSubmitting}>
          {isSubmitting ? 'Analyzing Pre-Reveal Canon...' : 'Validate Theory Grounding'}
        </button>
      </form>

      {errorMsg && <div className="alert error">{errorMsg}</div>}

      {result && (
        <div className="theory-result-box" data-testid="theory-result">
          <h3>Validation Result: <span className={`verdict-tag ${result.validation_verdict.toLowerCase()}`}>{result.validation_verdict}</span></h3>
          <div className="grounding-meter">
            <span>Grounding Score:</span>
            <strong>{(result.grounding_score * 100).toFixed(0)}%</strong>
          </div>

          {result.supporting_evidence && result.supporting_evidence.length > 0 && (
            <div className="supporting-evidence-list">
              <h4>Supporting Evidence in Canon:</h4>
              <ul>
                {result.supporting_evidence.map((eid, idx) => (
                  <li key={idx}>{typeof eid === 'string' ? eid : JSON.stringify(eid)}</li>
                ))}
              </ul>
            </div>
          )}

          {result.missing_evidence && result.missing_evidence.length > 0 && (
            <div className="missing-evidence-list">
              <h4>Unobserved Claims / Missing Evidence:</h4>
              <ul>
                {result.missing_evidence.map((mid, idx) => (
                  <li key={idx}>
                    {typeof mid === 'string'
                      ? mid
                      : mid.proposition || mid.type || JSON.stringify(mid)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
