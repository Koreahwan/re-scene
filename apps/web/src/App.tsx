import React, { useState, useEffect, useCallback, useRef } from 'react';
import { confirmNavigation, loginDestination } from './utils/navigation';
import { LocaleProvider, useLocale } from './i18n/LocaleProvider';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Navbar } from './components/Navbar';
import { Footer } from './components/Footer';
import { HomePage } from './pages/HomePage';
import { BoxOfficeFilmPage } from './pages/BoxOfficeFilmPage';
import { FilmHubPage } from './pages/FilmHubPage';
import { FilmMorePage } from './pages/FilmMorePage';
import { RevealPage } from './pages/RevealPage';
import { ProofDetailPage } from './pages/ProofDetailPage';
import { RewatchPage } from './pages/RewatchPage';
import { TheoryLabPage } from './pages/TheoryLabPage';
// Standalone CommunityPage removed for Phase 1 - community reviews integrated into film pages
import { PostDetailPage } from './pages/PostDetailPage';
import { TopicDetailPage } from './pages/TopicDetailPage';
import { MyPage } from './pages/MyPage';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { AudienceLabPage } from './pages/AudienceLabPage';
import { MagazinePage } from './pages/MagazinePage';
import { MagazineDetailPage } from './pages/MagazineDetailPage';
import { getReleaseMode, isAuthAvailable } from './utils/featureAvailability';
import { NoticePage } from './pages/NoticePage';
import { isVisualFixtureMode } from './testing/useVisualFixture';

const getFullLocation = () => {
  if (typeof window === 'undefined') return '/';
  return (window.location.pathname || '/') + (window.location.search || '');
};

interface Phase2NoticeProps {
  icon: string;
  title: string;
  description: string;
  actionText?: string;
  actionPath?: string;
  navigate: (path: string) => void;
}

const Phase2NoticeView: React.FC<Phase2NoticeProps> = ({
  icon,
  title,
  description,
  actionText = 'Return to Home →',
  actionPath = '/',
  navigate,
}) => (
  <div style={{ maxWidth: '640px', margin: '100px auto', textAlign: 'center', padding: '0 24px' }}>
    <div style={{ fontSize: '48px', marginBottom: '16px' }}>{icon}</div>
    <h2 style={{ fontSize: '24px', color: '#2D2D34', margin: '0 0 12px 0', fontFamily: 'Pretendard, sans-serif' }}>
      {title}
    </h2>
    <p style={{ color: '#898992', fontSize: '15px', lineHeight: 1.6, marginBottom: '28px', fontFamily: 'Pretendard, sans-serif', whiteSpace: 'pre-line' }}>
      {description}
    </p>
    <button
      onClick={() => navigate(actionPath)}
      style={{
        background: '#2D2D34',
        border: 'none',
        color: '#FFFFFF',
        padding: '12px 24px',
        borderRadius: '8px',
        fontWeight: 600,
        fontSize: '14px',
        cursor: 'pointer',
        fontFamily: 'Pretendard, sans-serif',
      }}
    >
      {actionText}
    </button>
  </div>
);

const CommunityRedirect: React.FC<{ navigate: (path: string) => void }> = ({ navigate }) => {
  useEffect(() => {
    navigate('/films');
  }, [navigate]);
  return null;
};

const AppContent: React.FC = () => {
  const { demoAccount } = useAuth();
  const [currentPath, setCurrentPath] = useState<string>(getFullLocation);
  const { t } = useLocale();

  const acceptedLocation = useRef(getFullLocation());
  const historyIndex = useRef(Number(window.history.state?.resceneIndex || 0));
  const restoringHistory = useRef(false);
  const navigate = useCallback((path: string, alreadyConfirmed = false) => {
    if (path === '/login') path = loginDestination();
    if (!alreadyConfirmed && !confirmNavigation(path)) return;
    historyIndex.current += 1;
    window.history.pushState({ resceneIndex: historyIndex.current }, '', path);
    acceptedLocation.current = getFullLocation();
    setCurrentPath(getFullLocation());
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    window.history.replaceState({ ...window.history.state, resceneIndex: historyIndex.current }, '', window.location.href);
    const handlePopState = (event: PopStateEvent) => {
      if (restoringHistory.current) { restoringHistory.current = false; return; }
      const next = getFullLocation();
      const nextIndex = event.state?.resceneIndex;
      if (!confirmNavigation(next)) {
        if (typeof nextIndex === 'number' && nextIndex !== historyIndex.current) {
          restoringHistory.current = true;
          window.history.go(historyIndex.current - nextIndex);
        } else {
          window.history.pushState({ resceneIndex: historyIndex.current }, '', acceptedLocation.current);
        }
        return;
      }
      historyIndex.current = typeof nextIndex === 'number' ? nextIndex : historyIndex.current - 1;
      acceptedLocation.current = next;
      setCurrentPath(getFullLocation());
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const queryIndex = currentPath.indexOf('?');
  const pathname =
    queryIndex === -1 ? currentPath : currentPath.slice(0, queryIndex);
  const rawSearch =
    queryIndex === -1 ? '' : currentPath.slice(queryIndex + 1);
  const searchParams = new URLSearchParams(rawSearch);

  const isFilmMoreRoute =
    pathname === '/films' &&
    searchParams.get('modal') === 'all';

  const isFilmSearchRoute =
    pathname === '/films' &&
    !isFilmMoreRoute &&
    searchParams.has('q');

  const renderRoute = () => {
    if (pathname === '/' || pathname === '') {
      return <HomePage navigate={navigate} />;
    }

    if (pathname === '/notice') return <NoticePage navigate={navigate} />;

    if (pathname === '/box-office/film') {
      return <BoxOfficeFilmPage key={`${searchParams.get('title')}:${searchParams.get('pageId')}`} title={searchParams.get('title') || ''} pageId={searchParams.get('pageId')} navigate={navigate} />;
    }

    // Match /audience-lab
    if (pathname.startsWith('/audience-lab')) {
      if (getReleaseMode() === 'public_read_only') {
        return <Phase2NoticeView icon="📊" title="Audience Lab"
          description="Audience simulation is not enabled on this public release."
          navigate={navigate} />;
      }
      return <AudienceLabPage navigate={navigate} />;
    }

    // Match /magazine/:articleId
    const magMatch = pathname.match(/^\/magazine\/([^/]+)/);
    if (magMatch) {
      return <MagazineDetailPage articleId={magMatch[1]} navigate={navigate} />;
    }

    // Match /magazine
    if (pathname.startsWith('/magazine')) {
      return <MagazinePage navigate={navigate} />;
    }

    // Priority for /films
    // 1. isFilmMoreRoute -> FilmMorePage
    // 2. isFilmSearchRoute -> HomePage with search query
    // 3. otherwise -> FilmHubPage
    if (pathname === '/films') {
      if (isFilmMoreRoute) {
        return <FilmMorePage navigate={navigate} />;
      }
      if (isFilmSearchRoute) {
        return <HomePage navigate={navigate} searchQuery={searchParams.get('q') ?? ''} />;
      }
      return <FilmHubPage navigate={navigate} />;
    }

    // Match /films/:movieId/reveals/:revealId
    const revealMatch = pathname.match(/^\/films\/([^/]+)\/reveals\/([^/]+)/);
    if (revealMatch) {
      return <RevealPage movieId={revealMatch[1]} revealId={revealMatch[2]} navigate={navigate} />;
    }

    // Match /films/:movieId
    const filmMatch = pathname.match(/^\/films\/([^/]+)/);
    if (filmMatch) {
      return <FilmHubPage movieId={filmMatch[1]} navigate={navigate} />;
    }

    // Match /proofs/:proofId or /moments/:proofId
    const proofMatch = pathname.match(/^\/(?:proofs|moments)\/([^/]+)/);
    if (proofMatch) {
      return <ProofDetailPage proofId={proofMatch[1]} navigate={navigate} />;
    }

    const isPhase1PublicOnly = getReleaseMode() === 'public_read_only';

    // Match /rewatch/:journeyId
    const rewatchMatch = pathname.match(/^\/rewatch(?:\/([^/]+))?/);
    if (rewatchMatch) {
      return <RewatchPage journeyId={rewatchMatch[1] || 'tbw-journey-01'} revealId={searchParams.get('reveal_id') || undefined} workId={searchParams.get('work_id') || undefined} navigate={navigate} />;
    }

    // Match /theory-lab
    if (pathname.startsWith('/theory-lab')) {
      if (isPhase1PublicOnly) {
        return (
          <Phase2NoticeView
            icon="🔬"
            title="Theory Lab (Phase 2 Preview)"
            description={"Fan theory submission and verification analysis features are planned for Phase 2.\nPhase 1 focuses on the film catalog and magazine exploration."}
            actionText="Explore Films →"
            actionPath="/films"
            navigate={navigate}
          />
        );
      }
      const revId = searchParams.get('reveal_id') || 'reveal-anderson-identity';
      return <TheoryLabPage initialRevealId={revId} navigate={navigate} />;
    }

    // Match /posts/:postId
    const postMatch = pathname.match(/^\/posts\/([^/]+)/);
    if (postMatch) {
      return <CommunityRedirect navigate={navigate} />;
    }

    // Match /community -> Cleanly guide to film exploration
    if (pathname.startsWith('/community')) {
      return <CommunityRedirect navigate={navigate} />;
    }

    // Match /me or /profile
    if (pathname.startsWith('/me') || pathname.startsWith('/profile')) {
      return <MyPage navigate={navigate} />;
    }

    // Match /login
    if (pathname === '/login') {
      if (!isAuthAvailable()) {
        return <HomePage navigate={navigate} />;
      }
      return <LoginPage navigate={navigate} />;
    }

    // Match /signup
    if (pathname === '/signup') {
      if (demoAccount.enabled) return <LoginPage navigate={navigate} />;
      if (!isAuthAvailable()) {
        return <HomePage navigate={navigate} />;
      }
      return <SignupPage navigate={navigate} />;
    }

    // Match /forgot-password or /reset-password
    if (pathname === '/forgot-password' || pathname === '/reset-password') {
      return <section className="auth-page"><div className="auth-panel">
        <h1>Forgot Password</h1><p role="status">Password reset is not available yet.</p>
        <button className="auth-submit" onClick={() => navigate(loginDestination(searchParams.get('next') || '/films'))}>Back to Log In</button>
      </div></section>;
    }

    // Default 404
    return (
      <div
        data-testid="page-not-found"
        style={{
          maxWidth: '640px',
          margin: '80px auto',
          textAlign: 'center',
          padding: '0 24px',
        }}
      >
        <div style={{ fontSize: '48px', marginBottom: '16px' }} aria-hidden="true">🎞️</div>
        <h2
          data-testid="not-found-heading"
          style={{
            fontSize: '24px',
            color: '#111827',
            margin: '0 0 12px 0',
            fontWeight: 700,
            fontFamily: 'Pretendard, -apple-system, sans-serif',
          }}
        >
          Scene Not Found (404)
        </h2>
        <p
          style={{
            color: '#4B5563',
            fontSize: '15px',
            lineHeight: '1.6',
            marginBottom: '28px',
            fontFamily: 'Pretendard, -apple-system, sans-serif',
          }}
        >
          The requested narrative page or proof does not exist in the canon index.
        </p>
        <button
          type="button"
          data-testid="not-found-back-button"
          onClick={() => navigate('/')}
          style={{
            background: '#111827',
            border: '1px solid #111827',
            color: '#FFFFFF',
            padding: '12px 24px',
            borderRadius: '8px',
            fontWeight: 600,
            fontSize: '15px',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            outline: 'none',
          }}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow = '0 0 0 3px rgba(76, 34, 244, 0.4)';
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
          }}
        >
          {t('common.back') || 'Return to Home'} →
        </button>
      </div>
    );
  };

  const isFixtureMode = isVisualFixtureMode();
  const isLightModeRoute = pathname === '/' || isFilmSearchRoute || pathname.startsWith('/films') || pathname.startsWith('/magazine') || pathname.startsWith('/proofs');

  return (
    <div
      className={isFixtureMode ? `fixture-override-global fixture-path-${currentPath.replace(/[^a-zA-Z0-9]/g, '-')}` : 'live-product'}
      style={{
        minHeight: '100vh',
        background: isLightModeRoute ? '#FFFFFF' : 'var(--bg-app, #0A0D14)',
        color: isLightModeRoute ? '#2D2D34' : 'var(--text-primary, #FFFFFF)',
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
      }}
    >
      <Navbar currentPath={currentPath} navigate={navigate} />
      {import.meta.env.VITE_LOCAL_PREVIEW === 'true' && <aside aria-label="Local preview mode" style={{padding: '8px 24px', background: '#F0EDFF', color: '#4A3890', fontSize: 13}}>
        Local preview mode · External network calls and paid models blocked · Clue retrieval runs in keyword mode · Dev inbox handles auth emails.
      </aside>}
      <main style={{ flex: 1, width: '100%' }}>
        {renderRoute()}
      </main>
      <Footer navigate={navigate} />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <LocaleProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </LocaleProvider>
  );
};

