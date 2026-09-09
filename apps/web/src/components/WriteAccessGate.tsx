import React from 'react';
import { useAuth } from '../context/AuthContext';

export function WriteAccessGate({ children, navigate }: {
  children: React.ReactNode; navigate?: (path: string) => void;
}) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <p role="status">Checking sign-in…</p>;
  if (!isAuthenticated) return <p className="write-login-notice" data-testid="write-login-required">
    Log in to write analyses, reviews, comments or replies.{' '}
    <a href="/login" onClick={event => { if (navigate) { event.preventDefault(); navigate('/login'); } }}>Log In</a>
  </p>;
  return <>{children}</>;
}
