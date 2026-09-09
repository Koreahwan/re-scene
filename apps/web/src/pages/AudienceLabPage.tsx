import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/apiClient';

interface PersonaSummary {
  dataset_id: string;
  dataset_revision: string;
  license: string;
  sample_size: number;
  available_lenses: string[];
  age_distribution: Record<string, number>;
  region_distribution: Record<string, number>;
  occupation_distribution: Record<string, number>;
  fairness_firewall: string;
  disclaimer: string;
}

interface AudienceLabPageProps {
  navigate?: (path: string) => void;
}

export const AudienceLabPage: React.FC<AudienceLabPageProps> = () => {
  const [summary, setSummary] = useState<PersonaSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [simulating, setSimulating] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'funnel' | 'bottlenecks' | 'cohorts' | 'sensitivity' | 'demand' | 'load' | 'traces'>('funnel');

  // Simulation config form & session state
  const [simResult, setSimResult] = useState<any>(null);
  const [completedRunId, setCompletedRunId] = useState<string | null>(() => sessionStorage.getItem('audience_lab_completed_run_id'));
  const [activeRunId, setActiveRunId] = useState<string | null>(() => sessionStorage.getItem('audience_lab_active_run_id'));
  const [isBackgroundRunning, setIsBackgroundRunning] = useState<boolean>(false);
  const [selectedMode, setSelectedMode] = useState<string>('DEMO_US');
  const [personasCount, setPersonasCount] = useState<number>(100000);
  const [replications, setReplications] = useState<number>(10);
  const [cohortView, setCohortView] = useState<'balanced' | 'weighted'>('balanced');
  const [monthlyVisitors, setMonthlyVisitors] = useState<number>(50000);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const abortControllerRef = React.useRef<AbortController | null>(null);
  const seedKeyRef = React.useRef<string>(`idem-seed-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`);

  useEffect(() => {
    loadData();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const sum = await apiClient.audienceLab.getPersonasSummary();
      setSummary(sum);

      const savedCompleted = sessionStorage.getItem('audience_lab_completed_run_id');
      if (savedCompleted) {
        setCompletedRunId(savedCompleted);
        setActionMsg(`Recovered completed simulation run ${savedCompleted}.`);
      }

      const savedActive = sessionStorage.getItem('audience_lab_active_run_id');
      if (savedActive) {
        try {
          const runStatus = await apiClient.audienceLab.getRun(savedActive);
          if (runStatus.status === 'COMPLETED') {
            setCompletedRunId(savedActive);
            sessionStorage.setItem('audience_lab_completed_run_id', savedActive);
            setSimResult(runStatus.result);
            sessionStorage.removeItem('audience_lab_active_run_id');
            setActiveRunId(null);
            setActionMsg(`Recovered completed simulation run ${savedActive}.`);
          } else if (runStatus.status === 'FAILED' || runStatus.status === 'ABSTAINED') {
            sessionStorage.removeItem('audience_lab_active_run_id');
            setActiveRunId(null);
          } else {
            setActiveRunId(savedActive);
            setIsBackgroundRunning(true);
            setActionMsg(`Active simulation ${savedActive} is running in background. Click 'Resume Polling' to track progress.`);
          }
        } catch {}
      }

      if (!simResult) {
        try {
          const latest = await apiClient.audienceLab.getLatestSummary();
          setSimResult(latest);
        } catch {
          setSimResult(null);
        }
      }
    } catch (err: any) {
      console.error('Failed to load Audience Lab data', err);
    } finally {
      setLoading(false);
    }
  };

  const pollRun = async (runId: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setSimulating(true);
    setIsBackgroundRunning(false);
    setActionMsg(`시뮬레이션 실행 중입니다 (Run ID: ${runId})...`);

    const startTime = Date.now();
    let terminal = false;

    try {
      while (!terminal && !ac.signal.aborted && (Date.now() - startTime) < 180000) {
        await new Promise((r) => setTimeout(r, 1500));
        if (ac.signal.aborted) break;

        const fullRun = await apiClient.audienceLab.getRun(runId);
        if (fullRun.status === 'COMPLETED') {
          terminal = true;
          setCompletedRunId(runId);
          sessionStorage.setItem('audience_lab_completed_run_id', runId);
          sessionStorage.removeItem('audience_lab_active_run_id');
          setActiveRunId(null);
          setSimResult(fullRun.result);
          setActionMsg(
            `시뮬레이션이 성공적으로 완료되었습니다 (Run ${runId}: ${fullRun.result?.synthetic_sessions?.toLocaleString()} 세션 / ${fullRun.result?.runtime_seconds}초).`
          );
        } else if (fullRun.status === 'FAILED' || fullRun.status === 'ABSTAINED') {
          terminal = true;
          sessionStorage.removeItem('audience_lab_active_run_id');
          setActiveRunId(null);
          setActionMsg(`시뮬레이션 종료 (${fullRun.status}): ${fullRun.error_message || 'No details'}`);
        } else {
          setActionMsg(`시뮬레이션 실행 중 (Run ID: ${runId}, 상태: ${fullRun.status})...`);
        }
      }

      if (!terminal && !ac.signal.aborted) {
        setIsBackgroundRunning(true);
        setActionMsg(`폴링 대기 시간 초과. 시뮬레이션 ${runId}은 백그라운드에서 계속 실행됩니다.`);
      }
    } catch (err: any) {
      if (!ac.signal.aborted) {
        setIsBackgroundRunning(true);
        setActionMsg(`폴링 일시 중단: ${err.message || 'Network delay'}.`);
      }
    } finally {
      setSimulating(false);
    }
  };

  const handleRunSimulation = async () => {
    try {
      setSimulating(true);
      setActionMsg('시뮬레이션 대기열 등록 중...');
      const res = await apiClient.audienceLab.createRun({
        mode: selectedMode,
        unique_source_personas: personasCount,
        replications: replications,
        seed: 42,
      });
      const runId = res.run_id;
      setActiveRunId(runId);
      sessionStorage.setItem('audience_lab_active_run_id', runId);
      await pollRun(runId);
    } catch (err: any) {
      setActionMsg(`시뮬레이션 등록 실패: ${err.message || 'Error executing run'}`);
      setSimulating(false);
    }
  };

  const handleResumePolling = () => {
    if (activeRunId) {
      pollRun(activeRunId);
    }
  };

  const handleCancelPolling = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setSimulating(false);
    setIsBackgroundRunning(true);
    setActionMsg(`폴링 일시 중지됨. Run ${activeRunId || completedRunId}은 백그라운드에서 계속됩니다.`);
  };

  const handleSeedDemoContent = async () => {
    const targetRunId = completedRunId || activeRunId;
    if (!targetRunId) {
      setActionMsg('먼저 시뮬레이션 실행을 완료하여 run ID를 획득해주세요.');
      return;
    }
    try {
      setActionMsg(`데모 콘텐츠 생성 중 (Run: ${targetRunId})...`);
      const res = await apiClient.audienceLab.seedContent(
        targetRunId,
        {
          posts_count: 20,
          comments_count: 40,
          counterclaims_count: 20,
          reactions_count: 60,
          enable_magazine: true,
        },
        seedKeyRef.current
      );
      setActionMsg(`데모 콘텐츠가 생성되었습니다: ${JSON.stringify(res.seeded_counts || res.summary || res)}`);
    } catch (err: any) {
      setActionMsg(`생성 실패: ${err.message || 'Error'}`);
    }
  };

  const handlePurgeDemoContent = async () => {
    if (!window.confirm('모든 인공 데모 데이터를 삭제하시겠습니까? 실제 데이터는 보존됩니다.')) {
      return;
    }
    try {
      setActionMsg('데모 데이터 삭제 중...');
      const res = await apiClient.audienceLab.purgeContent(true);
      setActionMsg(`삭제 완료: ${JSON.stringify(res.purged_counts)}`);
    } catch (err: any) {
      setActionMsg(`삭제 실패: ${err.message || 'Error'}`);
    }
  };

  const aggregateFunnel = simResult?.aggregate_funnel;
  const bottlenecks = simResult?.bottlenecks?.bottlenecks || [];
  const cohorts = cohortView === 'balanced' ? (simResult?.balanced_eval_cohorts || []) : (simResult?.source_weighted_cohorts || []);
  const sensitivity = simResult?.sensitivity?.results || [];
  const traces = simResult?.representative_traces || [];

  return (
    <div className="page-container">
      <div className="page-content" style={{ maxWidth: '1280px', gap: '28px' }}>
        {/* Header */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <h1 style={{ fontSize: '26px', fontWeight: 700, color: '#2D2D34', margin: 0 }}>
              USA Synthetic Audience Lab
            </h1>
            <span style={{ background: '#4C22F4', color: '#FFFFFF', fontSize: '11px', fontWeight: 700, padding: '3px 8px', borderRadius: '4px' }}>
              ADMIN EVALUATION
            </span>
          </div>
          <p style={{ color: '#888888', fontSize: '14px', margin: 0 }}>
            NVIDIA Nemotron-Personas-USA 데이터셋 기반 대규모 관람객 행동 시뮬레이션
          </p>
        </div>

        {/* Action Message Alert */}
        {actionMsg && (
          <div data-testid="action-message" style={{ background: '#F0EDFF', border: '1px solid #4C22F4', borderRadius: '8px', padding: '12px 16px', color: '#4C22F4', fontSize: '13px' }}>
            {actionMsg}
          </div>
        )}

        {/* Top Metrics Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
          <div style={{ background: '#FFFFFF', padding: '16px', borderRadius: '8px', border: '1px solid #EEEEEE' }}>
            <div style={{ fontSize: '12px', color: '#888888', textTransform: 'uppercase', marginBottom: '4px' }}>데이터셋</div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#2D2D34' }}>{summary?.dataset_id || 'Nemotron-Personas-USA'}</div>
            <div style={{ fontSize: '11px', color: '#888888', marginTop: '2px' }}>Rev: {summary?.dataset_revision || '5b4cd35'}</div>
          </div>

          <div style={{ background: '#FFFFFF', padding: '16px', borderRadius: '8px', border: '1px solid #EEEEEE' }}>
            <div style={{ fontSize: '12px', color: '#888888', textTransform: 'uppercase', marginBottom: '4px' }}>고유 페르소나</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: '#4C22F4' }}>
              {simResult ? simResult.unique_source_personas.toLocaleString() : (summary?.sample_size?.toLocaleString() || '10,000')}
            </div>
          </div>

          <div style={{ background: '#FFFFFF', padding: '16px', borderRadius: '8px', border: '1px solid #EEEEEE' }}>
            <div style={{ fontSize: '12px', color: '#888888', textTransform: 'uppercase', marginBottom: '4px' }}>시뮬레이션 세션</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: '#2D2D34' }}>
              {simResult ? simResult.synthetic_sessions.toLocaleString() : (loading ? '불러오는 중...' : '30,000')}
            </div>
          </div>

          <div style={{ background: '#FFFFFF', padding: '16px', borderRadius: '8px', border: '1px solid #EEEEEE' }}>
            <div style={{ fontSize: '12px', color: '#888888', textTransform: 'uppercase', marginBottom: '4px' }}>수렴 상태</div>
            <div style={{ fontSize: '14px', fontWeight: 700, color: '#27AE60' }}>
              {simResult?.convergence_status ? 'CONVERGED (Δ < 0.1%)' : 'STABLE BASELINE'}
            </div>
          </div>
        </div>

        {/* Simulation Controls Bar */}
        <div style={{ background: '#FFFFFF', border: '1px solid #EEEEEE', borderRadius: '8px', padding: '20px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#2D2D34', marginTop: 0, marginBottom: '16px' }}>
            시뮬레이션 제어
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center' }}>
            <div>
              <label style={{ fontSize: '12px', color: '#888888', display: 'block', marginBottom: '4px' }}>모드</label>
              <select
                data-testid="mode-select"
                aria-label="Simulation Mode"
                value={selectedMode}
                onChange={(e) => {
                  setSelectedMode(e.target.value);
                  if (e.target.value === 'CI') { setPersonasCount(10000); setReplications(1); }
                  else if (e.target.value === 'SMOKE') { setPersonasCount(10000); setReplications(2); }
                  else if (e.target.value === 'DEMO_US') { setPersonasCount(100000); setReplications(10); }
                  else if (e.target.value === 'FULL_US') { setPersonasCount(100000); setReplications(5); }
                }}
                style={{ background: '#FFFFFF', color: '#2D2D34', border: '1px solid #E5E5E5', borderRadius: '6px', padding: '8px 12px', fontSize: '13px' }}
              >
                <option value="CI">CI (10k personas / 30k sess)</option>
                <option value="SMOKE">SMOKE (10k personas / 100k sess)</option>
                <option value="DEMO_US">DEMO_US (100k personas / 5M sess)</option>
                <option value="FULL_US">FULL_US (Full Universe)</option>
              </select>
            </div>

            <div style={{ display: 'flex', gap: '10px', marginTop: '18px', flexWrap: 'wrap' }}>
              <button
                data-testid="run-sim-btn"
                onClick={handleRunSimulation}
                disabled={simulating}
                style={{ background: '#4C22F4', color: '#FFFFFF', border: 'none', borderRadius: '6px', padding: '8px 18px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                {simulating ? '실행 중...' : '시뮬레이션 실행'}
              </button>
              {simulating && (
                <button
                  data-testid="pause-polling-btn"
                  onClick={handleCancelPolling}
                  style={{ background: '#F2994A', color: '#FFFFFF', border: 'none', borderRadius: '6px', padding: '8px 14px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  폴링 일시 중지
                </button>
              )}
              {isBackgroundRunning && !simulating && (
                <button
                  data-testid="resume-polling-btn"
                  onClick={handleResumePolling}
                  style={{ background: '#4C22F4', color: '#FFFFFF', border: 'none', borderRadius: '6px', padding: '8px 14px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  폴링 재개
                </button>
              )}
              <button
                data-testid="seed-demo-content-btn"
                onClick={handleSeedDemoContent}
                style={{ background: '#27AE60', color: '#FFFFFF', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                데모 콘텐츠 생성
              </button>
              <button
                data-testid="purge-demo-content-btn"
                onClick={handlePurgeDemoContent}
                style={{ background: '#EB5757', color: '#FFFFFF', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                데모 콘텐츠 삭제
              </button>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid #EEEEEE', gap: '8px' }}>
          {[
            { key: 'funnel', label: '전환 퍼널' },
            { key: 'bottlenecks', label: '주요 병목' },
            { key: 'cohorts', label: '코호트 분석' },
            { key: 'sensitivity', label: '민감도 분석' },
            { key: 'demand', label: '수요 예측' },
            { key: 'load', label: '부하 프로파일' },
            { key: 'traces', label: '대표 세션 추적' },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key as any)}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: activeTab === t.key ? '2px solid #4C22F4' : '2px solid transparent',
                color: activeTab === t.key ? '#4C22F4' : '#888888',
                padding: '10px 16px',
                fontSize: '14px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* TAB CONTENT: Funnel */}
        {activeTab === 'funnel' && aggregateFunnel && (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', marginBottom: '16px' }}>
              전환 퍼널 분석
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
              {[
                { label: 'Landing → Film Hub', rate: aggregateFunnel.landing_to_film_hub_rate },
                { label: 'Film Hub → Reveal Gate', rate: aggregateFunnel.film_hub_to_reveal_rate },
                { label: 'Spoiler Gate Completion', rate: aggregateFunnel.spoiler_gate_completion_rate },
                { label: 'Reveal → Deep Reframe', rate: aggregateFunnel.reveal_to_deep_reframe_rate },
                { label: 'Deep Reframe Read Rate', rate: aggregateFunnel.deep_reframe_read_rate },
                { label: 'Rewatch Adoption Rate', rate: aggregateFunnel.rewatch_start_rate },
                { label: 'Theory Completion Rate', rate: aggregateFunnel.theory_completion_rate },
                { label: 'Community Contribution Rate', rate: aggregateFunnel.community_contribution_rate },
                { label: 'Magazine Read Rate', rate: aggregateFunnel.magazine_read_rate },
                { label: 'Golden Path Completion', rate: aggregateFunnel.golden_path_completion_rate, highlight: true },
              ].map((step, idx) => (
                <div key={idx} style={{ background: '#FFFFFF', padding: '12px 16px', borderRadius: '6px', border: step.highlight ? '1px solid #4C22F4' : '1px solid #EEEEEE' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '13px' }}>
                    <span style={{ fontWeight: step.highlight ? 700 : 500, color: step.highlight ? '#4C22F4' : '#2D2D34' }}>{step.label}</span>
                    <span style={{ fontWeight: 700, color: '#2D2D34' }}>{(step.rate * 100).toFixed(1)}%</span>
                  </div>
                  <div style={{ width: '100%', height: '8px', background: '#F5F5F5', borderRadius: '4px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, step.rate * 100)}%`, height: '100%', background: step.highlight ? '#4C22F4' : '#888888', borderRadius: '4px' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB CONTENT: Bottlenecks */}
        {activeTab === 'bottlenecks' && (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', marginBottom: '16px' }}>
              주요 사용자 이탈 및 병목 구간
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {bottlenecks.map((b: any) => (
                <div key={b.rank} style={{ background: '#FFFFFF', padding: '14px 18px', borderRadius: '8px', border: '1px solid #EEEEEE', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontWeight: 700, color: '#4C22F4', marginRight: '10px' }}>#{b.rank}</span>
                    <strong style={{ color: '#2D2D34' }}>{b.state}</strong>
                    <div style={{ fontSize: '13px', color: '#888888', marginTop: '4px' }}>{b.primary_dropoff_reasons?.join(', ')}</div>
                  </div>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#2D2D34' }}>{b.affected_sessions?.toLocaleString()} 세션</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB CONTENT: Cohorts */}
        {activeTab === 'cohorts' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', margin: 0 }}>
                코호트별 전환율 분석
              </h3>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setCohortView('balanced')}
                  style={{
                    background: cohortView === 'balanced' ? '#4C22F4' : '#F5F5F5',
                    color: cohortView === 'balanced' ? '#FFFFFF' : '#555555',
                    border: 'none',
                    padding: '6px 12px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    cursor: 'pointer'
                  }}
                >
                  균형 평가 뷰
                </button>
                <button
                  onClick={() => setCohortView('weighted')}
                  style={{
                    background: cohortView === 'weighted' ? '#4C22F4' : '#F5F5F5',
                    color: cohortView === 'weighted' ? '#FFFFFF' : '#555555',
                    border: 'none',
                    padding: '6px 12px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    cursor: 'pointer'
                  }}
                >
                  가중치 적용 뷰
                </button>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {cohorts.map((c: any, idx: number) => (
                <div key={idx} style={{ background: '#FFFFFF', padding: '12px 16px', borderRadius: '6px', border: '1px solid #EEEEEE', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, color: '#2D2D34' }}>{c.cohort_key}</span>
                  <span style={{ color: '#4C22F4', fontWeight: 700 }}>완료율 {(c.golden_path_completion_rate * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB CONTENT: Sensitivity */}
        {activeTab === 'sensitivity' && (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', marginBottom: '16px' }}>
              민감도 분석 (±20% 변동 탄력성)
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sensitivity.map((s: any, idx: number) => (
                <div key={idx} style={{ background: '#FFFFFF', padding: '12px 16px', borderRadius: '6px', border: '1px solid #EEEEEE', display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, color: '#2D2D34' }}>{s.factor_name} ({s.perturbation})</span>
                  <span style={{ color: '#2D2D34' }}>Δ {(s.golden_path_delta * 100).toFixed(2)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB CONTENT: Demand */}
        {activeTab === 'demand' && (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', marginBottom: '16px' }}>
              월간 방문자 기반 수요 계산기
            </h3>
            <input
              type="range"
              min={5000}
              max={500000}
              step={5000}
              value={monthlyVisitors}
              onChange={(e) => setMonthlyVisitors(Number(e.target.value))}
              style={{ width: '100%', marginBottom: '16px', accentColor: '#4C22F4' }}
            />
            <div style={{ background: '#FFFFFF', padding: '16px', borderRadius: '8px', border: '1px solid #EEEEEE' }}>
              예상 월간 완료 세션: <strong>{Math.round(monthlyVisitors * (aggregateFunnel?.golden_path_completion_rate || 0.35)).toLocaleString()}</strong> 회
            </div>
          </div>
        )}

        {/* TAB CONTENT: Load */}
        {activeTab === 'load' && (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', marginBottom: '16px' }}>
              Locust 부하 프로파일
            </h3>
            <div style={{ background: '#FFFFFF', padding: '16px', borderRadius: '8px', border: '1px solid #EEEEEE', fontSize: '14px', color: '#555555' }}>
              92.5% Read / 7.5% Write 분산 프로파일이 적용되어 있습니다.
            </div>
          </div>
        )}

        {/* TAB CONTENT: Traces */}
        {activeTab === 'traces' && (
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#2D2D34', marginBottom: '16px' }}>
              대표 세션 추적 ({traces.length})
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {traces.slice(0, 10).map((tr: any, idx: number) => (
                <div key={idx} style={{ background: '#FFFFFF', padding: '12px 16px', borderRadius: '6px', border: '1px solid #EEEEEE', fontSize: '13px' }}>
                  <strong style={{ color: '#4C22F4' }}>{tr.session_id}</strong> - <span>{tr.dropoff_reason}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
