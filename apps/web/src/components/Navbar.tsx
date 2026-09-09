import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { isAuthAvailable, isCommunityAvailable } from '../utils/featureAvailability';
import closeSvg from '../assets/figma/close.svg';
import filmCoreLogoLight from '../assets/figma/film-core-logo-light.svg';
import filmCoreSearch from '../assets/figma/film-core-search.svg';
import { confirmNavigation } from '../utils/navigation';
import profileIcon from '../assets/figma/user.svg';

export interface NavbarProps {
  currentPath: string;
  navigate: (path: string, alreadyConfirmed?: boolean) => void;
  variant?: 'desktop' | 'mobile';
  state?: 'guest' | 'authenticated';
}

export const Navbar: React.FC<NavbarProps> = ({ currentPath, navigate }) => {
  const { user, isAuthenticated, logout, demoAccount } = useAuth();
  const [typedQuery, setTypedQuery] = useState<string | null>(null);
  const profileMenu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const dismiss = (event: Event) => {
      if ((event instanceof KeyboardEvent && event.key === 'Escape') || (event.type === 'pointerdown' && !profileMenu.current?.contains(event.target as Node))) profileMenu.current?.removeAttribute('open');
    };
    document.addEventListener('pointerdown', dismiss); document.addEventListener('keydown', dismiss);
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', dismiss); };
  }, []);

  const queryIndex = currentPath.indexOf('?');
  const pathname = queryIndex === -1 ? currentPath : currentPath.slice(0, queryIndex);
  const rawSearch = queryIndex === -1 ? '' : currentPath.slice(queryIndex + 1);
  const searchParams = new URLSearchParams(rawSearch);
  const queryFromLocation = searchParams.get('q') ?? '';

  const isFixtureMode = typeof import.meta !== 'undefined' && import.meta.env?.VITE_VISUAL_FIXTURE_MODE === 'true';

  // Reset typed query on external navigation
  useEffect(() => {
    setTypedQuery(null);
    profileMenu.current?.removeAttribute('open');
  }, [currentPath]);

  const initialSearchValue = isFixtureMode
    ? (queryFromLocation.toLowerCase() === 'whispers' ? 'whispers' : '')
    : queryFromLocation;

  const displayValue = typedQuery !== null ? typedQuery : initialSearchValue;

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const effectiveQuery = typedQuery !== null ? typedQuery : initialSearchValue;
    const q = effectiveQuery.trim();
    if (q) {
      navigate(`/films?q=${encodeURIComponent(q)}`);
    }
  };

  const navItems = [
    { label: 'Movies', path: '/films', isActive: currentPath.startsWith('/films') || currentPath.startsWith('/proofs') },
    { label: 'Magazine', path: '/magazine', isActive: currentPath.startsWith('/magazine') },
  ];

  return (
    <header
      data-testid="global-navbar"
      role="banner"
      className="film-core-navbar"
      style={{
        width: '100%',
        height: '90px',
        boxSizing: 'border-box',
        background: '#FFFFFF',
        padding: '20px clamp(16px, 6.25vw, 120px)',
        borderBottom: '1px solid #E9E8E6',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'relative',
        zIndex: 100,
      }}
    >
      {/* Left group */}
      <div
        className="film-core-nav-left"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '24px',
          flexShrink: 0,
        }}
      >
        <button
          data-testid="navbar-logo"
          onClick={() => navigate('/')}
          title="RE:SCENE"
          aria-label="Reframe Home"
          className="film-core-nav-logo-btn"
          style={{
            width: '118px',
            height: '40px',
            boxSizing: 'border-box',
            paddingTop: '1px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'none',
            border: 'none',
            paddingLeft: 0,
            paddingRight: 0,
            paddingBottom: 0,
            cursor: 'pointer',
          }}
        >
          <img
            src={filmCoreLogoLight}
            alt="RE:SCENE Logo"
            width="110.001"
            height="14.868"
            className="film-core-nav-logo-img"
            style={{
              width: '110.001px',
              height: '14.868px',
              display: 'block',
            }}
          />
        </button>

        <nav
          data-testid="navbar-nav"
          aria-label="Main Navigation"
          className="film-core-nav-links"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          {navItems.map((item) => (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className="film-core-nav-item-btn"
              style={{
                height: '32px',
                padding: '0 12px',
                fontFamily: 'Pretendard, -apple-system, sans-serif',
                fontSize: '16px',
                fontWeight: item.isActive ? 700 : 500,
                color: item.isActive ? '#2D2D34' : '#AFAFB8',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Right: Search Control & Auth State */}
      <div
        className="film-core-nav-right"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          flex: 1,
          justifyContent: 'flex-end',
          minWidth: 0,
        }}
      >
        <form
          data-testid="navbar-search"
          role="search"
          onSubmit={handleSearchSubmit}
          className="film-core-nav-search-form"
          style={{
            width: '100%',
            maxWidth: '534px',
            height: '50px',
            boxSizing: 'border-box',
            padding: '12px 20px',
            border: '1px solid #E6E6EA',
            borderRadius: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: '#FFFFFF',
          }}
        >
          <input
            type="text"
            aria-label="Search movies"
            placeholder="SEARCH"
            value={displayValue}
            onChange={(e) => setTypedQuery(e.target.value)}
            className="film-core-nav-search-input"
            style={{
              border: 'none',
              background: 'transparent',
              fontFamily: 'Pretendard, -apple-system, sans-serif',
              fontSize: '14px',
              fontWeight: 500,
              color: '#2D2D34',
              flex: 1,
              marginRight: '8px',
              outline: 'none',
            }}
          />
          {displayValue && (
            <button
              type="button"
              onClick={() => setTypedQuery('')}
              aria-label="Clear search"
              style={{
                background: 'none',
                border: 'none',
                padding: '0 4px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <img src={closeSvg} alt="" style={{ width: '14px', height: '14px', opacity: 0.5 }} />
            </button>
          )}
          <button
            type="submit"
            aria-label="Submit search"
            className="film-core-nav-search-btn"
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '24px',
              height: '24px',
            }}
          >
            <img
              src={filmCoreSearch}
              alt=""
              width="24"
              height="24"
              className="film-core-nav-search-img"
              style={{ width: '24px', height: '24px', display: 'block' }}
            />
          </button>
        </form>

        {/* Auth State Links */}
        {isAuthenticated ? (
          <details ref={profileMenu} className="nav-profile-menu" style={{ position: 'relative', flexShrink: 0 }}>
            <summary aria-label="Profile menu" style={{ cursor: 'pointer', listStyle: 'none', width: 40, height: 40, borderRadius: '50%', background: '#F2EEFF', display: 'grid', placeItems: 'center', color: '#4C22F4' }}>
              {user?.avatar_url ? <img src={user.avatar_url} alt="" style={{ width: 40, height: 40, borderRadius: '50%', objectFit: 'cover' }} /> : <img src={profileIcon} alt="" width={24} height={24} />}
            </summary>
            <div style={{ position: 'absolute', right: 0, top: 48, minWidth: 150, background: 'white', border: '1px solid #E6E6EA', borderRadius: 8, padding: 8, boxShadow: '0 4px 16px #0001', zIndex: 100 }}>
              <button className="nav-auth-btn" onClick={event => { event.currentTarget.closest('details')?.removeAttribute('open'); navigate('/me'); }} style={{ display: 'block', width: '100%', border: 0, background: 'none', textAlign: 'left', padding: 12, cursor: 'pointer' }}>My Page</button>
              <button className="nav-auth-btn" onClick={async event => { const button = event.currentTarget; if (!confirmNavigation('/logout')) return; button.disabled = true; try { await logout(); navigate('/login', true); } catch { button.disabled = false; window.alert('Unable to log out. Please try again.'); } }} style={{ display: 'block', width: '100%', border: 0, background: 'none', textAlign: 'left', padding: 12, cursor: 'pointer' }}>Log Out</button>
            </div>
          </details>
        ) : isAuthAvailable() ? (
          <div className="nav-auth-links" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <button
              onClick={() => navigate('/login')}
              className="nav-auth-btn"
              style={{
                padding: '8px 16px',
                background: 'none',
                border: 'none',
                fontFamily: 'Pretendard, -apple-system, sans-serif',
                fontSize: '14px',
                fontWeight: 500,
                color: '#2D2D34',
                cursor: 'pointer',
              }}
            >
              Log In
            </button>
            <button
              onClick={() => navigate(demoAccount.enabled ? '/login' : '/signup')}
              className="nav-auth-btn primary"
              style={{
                padding: '8px 16px',
                background: '#2D2D34',
                border: 'none',
                borderRadius: '8px',
                fontFamily: 'Pretendard, -apple-system, sans-serif',
                fontSize: '14px',
                fontWeight: 600,
                color: '#FFFFFF',
                cursor: 'pointer',
              }}
            >
              {demoAccount.enabled ? 'Try Demo' : 'Sign Up'}
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
};
