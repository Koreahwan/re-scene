import React, { useEffect, useState, useRef } from 'react';
import { RevealSummaryDTO, TheoryValidationResultDTO } from '../types/api';
import { apiClient } from '../services/apiClient';
import { ErrorState } from '../components/FeedbackStates';
import { useAuth } from '../context/AuthContext';
import { WriteAccessGate } from '../components/WriteAccessGate';

interface TheoryLabPageProps {
  initialRevealId?: string;
  navigate: (path: string) => void;
}

export const TheoryLabPage: React.FC<TheoryLabPageProps> = ({
  initialRevealId = 'reveal-anderson-identity',
  navigate
}) => {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const canWrite = () => {
    if (authLoading) return false;
    if (!isAuthenticated) { navigate('/login'); return false; }
    return true;
  };
  const [reveals, setReveals] = useState<RevealSummaryDTO[]>([]);
  const [targetRevealId, setTargetRevealId] = useState<string>(initialRevealId);
  const [title, setTitle] = useState<string>('');
  const [explanation, setExplanation] = useState<string>('');
  const [draftId, setDraftId] = useState<string | null>(null);
  const [versionNo, setVersionNo] = useState<number>(1);
  const [isSavingDraft, setIsSavingDraft] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [result, setResult] = useState<TheoryValidationResultDTO | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);

  const rememberDraft = (id: string, runId?: string) => {
    navigate(`/theory-lab?reveal_id=${encodeURIComponent(targetRevealId)}&theory_id=${encodeURIComponent(id)}${runId ? `&run_id=${encodeURIComponent(runId)}` : ''}`);
  };
  const checkRun = async (runId: string) => {
    try {
      const response = await apiClient.theory.getTheoryRun(runId);
      const status = response.data.status || 'UNKNOWN';
      setRunStatus(status);
      if (['COMPLETED', 'ABSTAINED', 'FAILED'].includes(status)) setResult(response.data);
      setStatusMessage(`실행 상태: ${response.data.status}`);
    } catch (error: any) { setErrorMsg(error.message); }
  };

  useEffect(() => {
    loadReveals();
    const query = new URLSearchParams(window.location.search);
    const savedId = query.get('theory_id');
    if (savedId) {
      apiClient.theory.getTheory(savedId).then(res => {
        if (res.data.status === 'PUBLISHED') { navigate(`/posts/${savedId}`); return; }
        setDraftId(savedId); setTitle(res.data.title); setExplanation(res.data.body_markdown);
        setVersionNo(res.data.version_no);
        if (res.data.target_reveal_id) setTargetRevealId(res.data.target_reveal_id);
      }).catch(error => setErrorMsg(error.message));
    }
    const savedRunId = query.get('run_id');
    if (savedRunId) { setLastRunId(savedRunId); checkRun(savedRunId); }
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const loadReveals = async () => {
    try {
      const res = await apiClient.catalog.getReveals('the-bat-whispers-1930');
      const list = res.data || [];
      setReveals(list);
      if (list.length > 0 && !targetRevealId) {
        setTargetRevealId(list[0].reveal_id);
      }
    } catch (err: any) {
      console.error('Failed to load reveals', err);
    }
  };

  const handleSaveDraft = async () => {
    if (!canWrite()) return;
    if (!title.trim() || !explanation.trim()) {
      setErrorMsg('제목과 가설 설명을 입력해주세요.');
      return;
    }
    setIsSavingDraft(true);
    setErrorMsg(null);
    try {
      if (!draftId) {
        const res = await apiClient.theory.createTheory({
          title: title.trim(),
          hypothesis_explanation: explanation.trim(),
          target_reveal_id: targetRevealId,
          work_id: 'the-bat-whispers-1930',
          edition_id: 'tbw-fullscreen-archive'
        });
        setDraftId(res.data.theory_id);
        rememberDraft(res.data.theory_id);
        setVersionNo(1);
        setStatusMessage(`임시저장 완료 (v1). Draft ID: ${res.data.theory_id}`);
      } else {
        const res = await apiClient.theory.updateTheory(draftId, {
          title: title.trim(),
          hypothesis_explanation: explanation.trim(),
          target_reveal_id: targetRevealId,
          change_summary: 'Updated draft from Theory Lab'
        });
        const nextVer = res.data?.version_no || (versionNo + 1);
        setVersionNo(nextVer);
        setStatusMessage(`임시저장 버전 v${nextVer} 저장 완료.`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || '임시저장에 실패했습니다.');
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handleValidate = async (e?: React.FormEvent) => {
    if (!canWrite()) { e?.preventDefault(); return; }
    if (e) e.preventDefault();
    if (!title.trim() || !explanation.trim()) {
      setErrorMsg('제목과 가설 내용을 작성해주세요.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setResult(null);
    setRunStatus('QUEUED');
    setStatusMessage('서사 검증 대기열 등록 중...');

    abortControllerRef.current = new AbortController();

    try {
      let activeDraftId = draftId;
      if (!activeDraftId) {
        const draftRes = await apiClient.theory.createTheory({
          title: title.trim(),
          hypothesis_explanation: explanation.trim(),
          target_reveal_id: targetRevealId,
          work_id: 'the-bat-whispers-1930',
          edition_id: 'tbw-fullscreen-archive'
        });
        activeDraftId = draftRes.data.theory_id;
        setDraftId(activeDraftId);
      } else {
        await apiClient.theory.updateTheory(activeDraftId, {
          title: title.trim(), hypothesis_explanation: explanation.trim(),
          target_reveal_id: targetRevealId,
        });
      }

      const runRes = await apiClient.theory.submitTheoryRun({
        theory_id: activeDraftId,
        target_reveal_id: targetRevealId,
        work_id: 'the-bat-whispers-1930',
        edition_id: 'tbw-fullscreen-archive'
      });
      const runId = runRes.data.run_id;
      setLastRunId(runId);
      rememberDraft(activeDraftId, runId);
      setRunStatus(runRes.data.status || 'QUEUED');

      let attempts = 0;
      const maxAttempts = 20;
      let delayMs = 600;

      while (attempts < maxAttempts) {
        if (abortControllerRef.current?.signal.aborted) break;
        await new Promise((r) => setTimeout(r, delayMs));
        attempts++;
        delayMs = Math.min(delayMs * 1.2, 2000);

        const checkRes = await apiClient.theory.getTheoryRun(runId);
        if (checkRes.data) {
          const currentStatus = checkRes.data.status || 'RUNNING';
          setRunStatus(currentStatus);

          if (currentStatus === 'RUNNING') {
            setStatusMessage('서사 기억 저장소와 가설의 일관성을 검증 중입니다...');
          } else if (currentStatus === 'COMPLETED' || currentStatus === 'ABSTAINED' || currentStatus === 'FAILED') {
            setResult(checkRes.data);
            setStatusMessage(`검색 완료: ${checkRes.data.validation_verdict || currentStatus}`);
            break;
          }
        }
      }
      if (attempts >= maxAttempts) setStatusMessage('실행이 계속되고 있습니다. 아래 상태 확인 버튼으로 결과를 다시 조회할 수 있습니다.');
    } catch (err: any) {
      setErrorMsg(err.message || '가설 검증에 실패했습니다.');
      setRunStatus('FAILED');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePublish = async () => {
    if (!canWrite()) return;
    if (!draftId) {
      setErrorMsg('가설을 먼저 임시저장하거나 검증해주세요.');
      return;
    }
    setIsPublishing(true);
    setErrorMsg(null);
    try {
      await apiClient.theory.updateTheory(draftId, {
        title: title.trim(), hypothesis_explanation: explanation.trim(),
        target_reveal_id: targetRevealId,
      });
      const postRes = await apiClient.theory.publishTheory(draftId);
      const newPostId = postRes.data.theory_id;
      setStatusMessage('가설이 커뮤니티에 등록되었습니다!');
      navigate(`/posts/${newPostId}`);
    } catch (err: any) {
      setErrorMsg(err.message || '가설 게시에 실패했습니다.');
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="page-container">
      <div className="page-content" style={{ maxWidth: '960px', gap: '28px' }}>
        {/* Header Card */}
        <div style={{
          background: '#FFFFFF',
          border: '1px solid #EEEEEE',
          borderRadius: '12px',
          padding: '32px',
          boxShadow: '0 2px 8px #00000008'
        }}>
          <div style={{
            display: 'inline-block',
            background: '#F0EDFF',
            color: '#4C22F4',
            padding: '4px 10px',
            borderRadius: '9999px',
            fontSize: '12px',
            fontWeight: 700,
            marginBottom: '12px'
          }}>
            THEMATIC REASONING ENGINE
          </div>
          <h1 style={{ fontSize: '26px', fontWeight: 700, color: '#2D2D34', margin: '0 0 12px 0' }}>
            서사 가설 및 복선 분석 연구소
          </h1>
          <p style={{ color: '#888888', fontSize: '14px', margin: 0, lineHeight: 1.6 }}>
            영화 속 숨은 복선과 가설을 제안하고 검증합니다.
            현재 로컬 모드는 한·영 핵심어로 관련 장면을 찾습니다. 가설의 참·거짓, 인과관계, 반사실 검증은 수행하지 않습니다.
          </p>
        </div>

        {/* Theory Form */}
        <div style={{
          background: '#FFFFFF',
          border: '1px solid #EEEEEE',
          borderRadius: '12px',
          padding: '32px',
          boxShadow: '0 2px 8px #00000008'
        }}>
          <WriteAccessGate navigate={navigate}>
          <form onSubmit={handleValidate} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#2D2D34', marginBottom: '8px' }}>
                대상 반전 순간
              </label>
              <select
                data-testid="target-reveal-select"
                aria-label="Target Reveal Milestone"
                value={targetRevealId}
                onChange={(e) => setTargetRevealId(e.target.value)}
                style={{
                  width: '100%',
                  background: '#FFFFFF',
                  border: '1px solid #E5E5E5',
                  color: '#2D2D34',
                  padding: '10px 14px',
                  borderRadius: '6px',
                  fontSize: '14px',
                  outline: 'none'
                }}
              >
                {reveals.map((r) => (
                  <option key={r.reveal_id} value={r.reveal_id}>
                    {r.safe_title || r.title} (기준 시점: {((r.spoiler_cutoff_ms || r.timestamp_ms || 4860000) / 60000).toFixed(1)}분)
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#2D2D34', marginBottom: '8px' }}>
                가설 제목
              </label>
              <input
                type="text"
                data-testid="theory-title-input"
                aria-label="Theory Title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="예: 벽난로 레버와 외부 창문 침입 구조에 관한 가설"
                required
                minLength={3}
                style={{
                  width: '100%',
                  background: '#FFFFFF',
                  border: '1px solid #E5E5E5',
                  color: '#2D2D34',
                  padding: '10px 14px',
                  borderRadius: '6px',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#2D2D34', marginBottom: '8px' }}>
                가설 및 근거 설명
              </label>
              <textarea
                rows={5}
                data-testid="theory-explanation-input"
                aria-label="Hypothesis and Premises Explanation"
                value={explanation}
                onChange={(e) => setExplanation(e.target.value)}
                placeholder="반전 시점 이전 장면에서 관찰되는 인물의 행동, 단서, 물리적 배경 등을 설명해주세요..."
                required
                minLength={10}
                style={{
                  width: '100%',
                  background: '#FFFFFF',
                  border: '1px solid #E5E5E5',
                  color: '#2D2D34',
                  padding: '10px 14px',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontFamily: 'inherit',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <button
                type="button"
                data-testid="save-draft-btn"
                onClick={handleSaveDraft}
                disabled={!isAuthenticated || isSavingDraft || isSubmitting || isPublishing}
                style={{
                  background: '#F5F5F5',
                  border: '1px solid #E5E5E5',
                  color: '#555555',
                  padding: '10px 20px',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '14px',
                  cursor: 'pointer'
                }}
              >
                {isSavingDraft ? '저장 중...' : (draftId ? `수정본 저장 (v${versionNo + 1})` : '임시저장')}
              </button>

              <button
                type="submit"
                data-testid="validate-theory-btn"
                disabled={!isAuthenticated || isSubmitting || isSavingDraft || isPublishing}
                style={{
                  background: '#4C22F4',
                  border: 'none',
                  color: '#FFFFFF',
                  padding: '10px 24px',
                  borderRadius: '6px',
                  fontWeight: 700,
                  fontSize: '14px',
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  opacity: isSubmitting ? 0.7 : 1
                }}
              >
                {isSubmitting ? '관련 장면 찾는 중...' : '관련 장면 찾기'}
              </button>

              {draftId && (
                <button
                  type="button"
                  data-testid="share-community-btn"
                  onClick={handlePublish}
                  disabled={isPublishing || isSubmitting}
                  style={{
                    background: '#27AE60',
                    border: 'none',
                    color: '#FFFFFF',
                    padding: '10px 20px',
                    borderRadius: '6px',
                    fontWeight: 600,
                    fontSize: '14px',
                    cursor: 'pointer'
                  }}
                >
                  {isPublishing ? '게시 중...' : '커뮤니티에 공유하기 →'}
                </button>
              )}
            </div>
          </form>
          </WriteAccessGate>

          {/* Status Badge */}
          {runStatus && (
            <div
              data-testid="theory-run-status-badge"
              style={{
                marginTop: '16px',
                padding: '8px 14px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                background: runStatus === 'COMPLETED' ? '#E8F5E9' : (runStatus === 'FAILED' ? '#FFEBEE' : '#F0EDFF'),
                color: runStatus === 'COMPLETED' ? '#27AE60' : (runStatus === 'FAILED' ? '#EB5757' : '#4C22F4'),
                border: `1px solid ${runStatus === 'COMPLETED' ? '#27AE6040' : (runStatus === 'FAILED' ? '#EB575740' : '#4C22F440')}`
              }}
            >
              <span>STATUS: {runStatus}</span>
            </div>
          )}

          {statusMessage && (
            <div data-testid="theory-status-message" style={{ marginTop: '12px', fontSize: '13px', color: '#888888' }}>
              {statusMessage}
            </div>
          )}
          {lastRunId && !isSubmitting && <button type="button" onClick={() => checkRun(lastRunId)} style={{marginTop: 12}}>실행 상태 다시 확인</button>}

          {errorMsg && <div style={{ marginTop: '16px' }}><ErrorState message={errorMsg} /></div>}
        </div>

        {/* Validation Result */}
        {result && (
          <div
            data-testid="theory-validation-result"
            style={{
              background: '#FFFFFF',
              border: '1px solid #EEEEEE',
              borderRadius: '12px',
              padding: '32px',
              boxShadow: '0 2px 8px #00000008'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#2D2D34', margin: 0 }}>
                관련 장면 검색 결과
              </h2>
              <span
                data-testid="validation-verdict-tag"
                style={{
                  background: result.validation_verdict === 'VALIDATED' || result.validation_verdict === 'SUPPORTED'
                    ? '#E8F5E9'
                    : '#FFF9C4',
                  color: result.validation_verdict === 'VALIDATED' || result.validation_verdict === 'SUPPORTED' ? '#27AE60' : '#F2994A',
                  padding: '4px 12px',
                  borderRadius: '6px',
                  fontWeight: 700,
                  fontSize: '13px'
                }}
              >
                {result.validation_verdict}
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '24px' }}>
              <div style={{ background: '#F8F9FA', padding: '16px', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', color: '#888888', textTransform: 'uppercase' }}>찾은 장면 근거 수</div>
                <div data-testid="grounding-score-display" style={{ fontSize: '22px', fontWeight: 700, color: '#4C22F4' }}>
                  {result.supporting_evidence?.length || 0}개
                </div>
              </div>
              <div style={{ background: '#F8F9FA', padding: '16px', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', color: '#888888', textTransform: 'uppercase' }}>불확실성 지수</div>
                <div style={{ fontSize: '22px', fontWeight: 700, color: '#F2994A' }}>
                  {result.uncertainty == null ? '측정 안 함' : `${(result.uncertainty * 100).toFixed(0)}%`}
                </div>
              </div>
              <div style={{ background: '#F8F9FA', padding: '16px', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', color: '#888888', textTransform: 'uppercase' }}>검증 모드</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#2D2D34' }}>
                  {result.validation_mode === 'LOCAL_KEYWORD_RETRIEVAL' ? '로컬 키워드 검색' : (result.validation_mode || '모드 정보 없음')}
                </div>
              </div>
              <div style={{ background: '#F8F9FA', padding: '16px', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', color: '#888888', textTransform: 'uppercase' }}>라이브 모델 지출</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#27AE60' }}>
                  {result.live_model_used ? 'Live API: Yes' : 'Live API: No ($0.00)'}
                </div>
              </div>
            </div>

            {result.supporting_evidence && result.supporting_evidence.length > 0 && (
              <div style={{ marginBottom: '20px' }}>
                <h3 style={{ fontSize: '14px', color: '#27AE60', textTransform: 'uppercase', marginBottom: '8px' }}>
                  함께 확인할 장면 ({result.supporting_evidence.length})
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {result.supporting_evidence.map((ev, idx) => (
                    <div key={idx} style={{ background: '#F8F9FA', padding: '10px 14px', borderRadius: '6px', fontSize: '13px', color: '#2D2D34' }}>
                      {(() => {
                        const detail = result.evidence_details?.find(item => item.event_id === ev);
                        return detail ? <><strong>{detail.scene_id}</strong><p>{detail.description}</p>
                          <button onClick={() => navigate(`/rewatch?reveal_id=${encodeURIComponent(targetRevealId)}&scene_id=${encodeURIComponent(detail.scene_id)}`)}>영상에서 확인</button></> : String(ev);
                      })()}
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
