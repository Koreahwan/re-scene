import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { UserProfileDTO } from '../types/api';
import { apiClient } from '../services/apiClient';
import { isAuthAvailable } from '../utils/featureAvailability';
import { clearReviewDrafts } from '../utils/reviewDraft';

interface AuthContextType {
  user: UserProfileDTO | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  loading: boolean;
  error: string | null;
  demoAccount: { enabled: boolean; email?: string; password?: string };
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, emailVerificationTicket: string, displayName?: string, handle?: string) => Promise<void>;
  logout: () => Promise<void>;
  devLogin: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfileDTO | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [demoAccount, setDemoAccount] = useState<{ enabled: boolean; email?: string; password?: string }>({ enabled: false });

  useEffect(() => {
    if (!isAuthAvailable()) return;
    let active = true;
    apiClient.auth.getDemoAccount().then(res => {
      if (active) setDemoAccount(res.data);
    }).catch(() => { /* Older servers retain the standard account flow. */ });
    return () => { active = false; };
  }, []);

  const refreshUser = useCallback(async () => {
    if (!isAuthAvailable()) {
      setUser(null);
      setLoading(false);
      setError(null);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      // Fetch CSRF token first
      await apiClient.auth.getCsrf();
      // Fetch current session profile
      const res = await apiClient.auth.getMe();
      setUser(res.data);
    } catch (err: any) {
      // Guest / unauthenticated is normal
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    if (!isAuthAvailable()) {
      const msg = '로그인 기능은 2차 공개 범위입니다.';
      setError(msg);
      throw new Error(msg);
    }
    setLoading(true);
    setError(null);
    try {
      await apiClient.auth.login({ email, password });
      await refreshUser();
    } catch (err: any) {
      setError(err.message || 'Login failed');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const signup = async (
    email: string,
    password: string,
    emailVerificationTicket: string,
    displayName?: string,
    handle?: string
  ) => {
    if (!isAuthAvailable()) {
      const msg = '회원가입 기능은 2차 공개 범위입니다.';
      setError(msg);
      throw new Error(msg);
    }
    setLoading(true);
    setError(null);
    try {
      await apiClient.auth.signup({
        email,
        password,
        email_verification_ticket: emailVerificationTicket,
        display_name: displayName,
        handle
      });
      await refreshUser();
    } catch (err: any) {
      setError(err.message || 'Signup failed');
      throw err;
    } finally {
      setLoading(false);
    }
  };


  const logout = async () => {
    setLoading(true);
    try {
      await apiClient.auth.logout();
      clearReviewDrafts();
      setUser(null);
    } catch (err: any) {
      console.error('Logout error', err);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const devLogin = async () => {
    if (!isAuthAvailable()) {
      setError('로그인 기능은 2차 공개 범위입니다.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await apiClient.auth.devLogin();
      await refreshUser();
    } catch (err: any) {
      setError(err.message || 'Dev login failed');
    } finally {
      setLoading(false);
    }
  };

  const isAuthenticated = !!user && user.role !== 'GUEST';
  const isAdmin = !!user && (user.role === 'ADMIN' || user.role === 'MODERATOR');

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isAdmin,
        loading,
        error,
        demoAccount,
        login,
        signup,
        logout,
        devLogin,
        refreshUser
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
