import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../i18n/LocaleProvider';
import { LanguageSelector } from './LanguageSelector';
import { apiClient } from '../services/apiClient';
import { getLocalizedErrorMessage } from '../utils/apiErrors';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: 'login' | 'signup' | 'forgot';
  onSuccess?: () => void;
}

const REMEMBER_EMAIL_KEY = 'rescene.rememberedEmail';

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  initialMode = 'login',
  onSuccess
}) => {
  const { login, signup } = useAuth();
  const { t } = useLocale();

  const [mode, setMode] = useState<'login' | 'signup' | 'forgot'>(initialMode);
  const [email, setEmail] = useState<string>(() => {
    try {
      return localStorage.getItem(REMEMBER_EMAIL_KEY) || '';
    } catch {
      return '';
    }
  });

  // Login & Shared State
  const [password, setPassword] = useState<string>('');
  const [passwordConfirm, setPasswordConfirm] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [rememberEmail, setRememberEmail] = useState<boolean>(() => {
    try {
      return !!localStorage.getItem(REMEMBER_EMAIL_KEY);
    } catch {
      return false;
    }
  });

  // Signup State
  const [nickname, setNickname] = useState<string>('');
  const [isCheckingNickname, setIsCheckingNickname] = useState<boolean>(false);
  const [nicknameChecked, setNicknameChecked] = useState<boolean>(false);
  const [nicknameStatusMsg, setNicknameStatusMsg] = useState<string | null>(null);

  const [verificationCode, setVerificationCode] = useState<string>('');
  const [signupTicket, setSignupTicket] = useState<string>('');
  const [isVerifyingEmail, setIsVerifyingEmail] = useState<boolean>(false);
  const [isConfirmingEmailCode, setIsConfirmingEmailCode] = useState<boolean>(false);
  const [emailCodeSent, setEmailCodeSent] = useState<boolean>(false);
  const [emailVerified, setEmailVerified] = useState<boolean>(false);
  const [emailStatusMsg, setEmailStatusMsg] = useState<string | null>(null);

  // Forgot Password State
  const [resetTicket, setResetTicket] = useState<string>('');
  const [resetCodeSent, setResetCodeSent] = useState<boolean>(false);
  const [resetCodeVerified, setResetCodeVerified] = useState<boolean>(false);
  const [isSendingResetCode, setIsSendingResetCode] = useState<boolean>(false);
  const [isVerifyingResetCode, setIsVerifyingResetCode] = useState<boolean>(false);
  const [newPassword, setNewPassword] = useState<string>('');
  const [newPasswordConfirm, setNewPasswordConfirm] = useState<string>('');

  // Form submission state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);
  const firstInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setMode(initialMode);
    setErrorMsg(null);
    setSuccessMsg(null);
  }, [initialMode, isOpen]);

  // Focus Lifecycle & Keyboard Trap
  useEffect(() => {
    if (isOpen) {
      previousActiveElementRef.current = document.activeElement as HTMLElement | null;
      document.body.style.overflow = 'hidden';

      // Focus first input on modal open
      setTimeout(() => {
        firstInputRef.current?.focus();
      }, 50);
    } else {
      document.body.style.overflow = '';
      if (previousActiveElementRef.current) {
        previousActiveElementRef.current.focus();
      }
    }

    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Escape key & Tab cycle trap
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === 'Tab' && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Clear verification when email input changes
  const handleEmailChange = (newEmail: string) => {
    setEmail(newEmail);
    setEmailVerified(false);
    setSignupTicket('');
    setVerificationCode('');
    setEmailCodeSent(false);
    setEmailStatusMsg(null);
    setResetCodeSent(false);
    setResetCodeVerified(false);
    setResetTicket('');
  };

  // --------------------------------------------------------------------------
  // Login Handler
  // --------------------------------------------------------------------------
  const handleSubmitLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      if (rememberEmail) {
        try {
          localStorage.setItem(REMEMBER_EMAIL_KEY, email.trim());
        } catch {}
      } else {
        try {
          localStorage.removeItem(REMEMBER_EMAIL_KEY);
        } catch {}
      }
      await login(email.trim(), password);
      onSuccess?.();
      onClose();
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsSubmitting(false);
    }
  };

  // --------------------------------------------------------------------------
  // Signup Handlers
  // --------------------------------------------------------------------------
  const handleRequestSignupVerification = async () => {
    if (!email.trim() || !email.includes('@')) {
      setEmailStatusMsg(t('auth.signup.invalidEmail'));
      return;
    }
    setIsVerifyingEmail(true);
    setEmailStatusMsg(null);
    try {
      await apiClient.auth.requestEmailVerification(email.trim());
      setEmailCodeSent(true);
      setEmailStatusMsg(t('auth.signup.codeSent'));
    } catch (err: any) {
      setEmailStatusMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsVerifyingEmail(false);
    }
  };

  const handleConfirmSignupCode = async () => {
    if (!verificationCode.trim()) return;
    setIsConfirmingEmailCode(true);
    try {
      const res = await apiClient.auth.confirmEmailVerification(email.trim(), verificationCode.trim());
      setEmailVerified(true);
      setSignupTicket(res.data.email_verification_ticket);
      setEmailStatusMsg(t('auth.signup.emailVerified'));
    } catch (err: any) {
      setEmailStatusMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsConfirmingEmailCode(false);
    }
  };

  const handleCheckNickname = async () => {
    const cleanNick = nickname.trim();
    if (!cleanNick) {
      setNicknameStatusMsg(t('auth.signup.nicknameRequired'));
      return;
    }
    setIsCheckingNickname(true);
    setNicknameStatusMsg(t('auth.signup.checkingHandle'));
    try {
      const res = await apiClient.auth.checkHandleAvailability(cleanNick);
      if (res.data.available) {
        setNicknameChecked(true);
        setNicknameStatusMsg(t('auth.signup.nicknameAvailable'));
      } else {
        setNicknameChecked(false);
        setNicknameStatusMsg(t('auth.signup.nicknameUnavailable'));
      }
    } catch (err: any) {
      setNicknameStatusMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsCheckingNickname(false);
    }
  };

  const handleSubmitSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return;

    if (!emailVerified || !signupTicket) {
      setErrorMsg(t('auth.error.emailNotVerified'));
      return;
    }

    if (password !== passwordConfirm) {
      setErrorMsg(t('auth.signup.passwordMismatch'));
      return;
    }

    if (password.length < 8) {
      setErrorMsg(t('auth.signup.passwordRule'));
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await signup(
        email.trim(),
        password,
        signupTicket,
        nickname.trim() || undefined,
        nickname.trim() || undefined
      );
      setSuccessMsg(t('auth.signup.success'));
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1200);
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsSubmitting(false);
    }
  };

  // --------------------------------------------------------------------------
  // Forgot Password Handlers
  // --------------------------------------------------------------------------
  const handleRequestResetCode = async () => {
    if (!email.trim() || !email.includes('@')) {
      setErrorMsg(t('auth.signup.invalidEmail'));
      return;
    }
    setIsSendingResetCode(true);
    setErrorMsg(null);
    try {
      await apiClient.auth.requestPasswordReset(email.trim());
      setResetCodeSent(true);
      setSuccessMsg(t('auth.forgot.codeSent'));
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsSendingResetCode(false);
    }
  };

  const handleVerifyResetCode = async () => {
    if (!verificationCode.trim()) return;
    setIsVerifyingResetCode(true);
    setErrorMsg(null);
    try {
      const res = await apiClient.auth.verifyPasswordReset(email.trim(), verificationCode.trim());
      setResetCodeVerified(true);
      setResetTicket(res.data.password_reset_ticket);
      setSuccessMsg(t('auth.forgot.codeVerified'));
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsVerifyingResetCode(false);
    }
  };

  const handleSubmitPasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetCodeVerified || !resetTicket) {
      setErrorMsg(t('auth.forgot.invalidCode'));
      return;
    }

    if (newPassword !== newPasswordConfirm) {
      setErrorMsg(t('auth.signup.passwordMismatch'));
      return;
    }

    if (newPassword.length < 8) {
      setErrorMsg(t('auth.signup.passwordRule'));
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await apiClient.auth.completePasswordReset(email.trim(), resetTicket, newPassword);
      setSuccessMsg(t('auth.forgot.resetSuccess'));
      setTimeout(() => {
        setMode('login');
        setSuccessMsg(null);
      }, 1500);
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'var(--bg-overlay, #0B0C10D9)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px'
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
        style={{
          width: '100%',
          maxWidth: mode === 'login' ? '440px' : '500px',
          background: 'var(--bg-modal, #161C2B)',
          border: '1px solid var(--border-strong, #FFFFFF40)',
          borderRadius: 'var(--radius-lg, 12px)',
          padding: '36px 28px',
          boxShadow: 'var(--shadow-lg, 0 10px 15px -3px #000000B2)',
          position: 'relative',
          boxSizing: 'border-box'
        }}
      >
        {/* Top Controls: Language Selector and Close Button */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          <LanguageSelector variant="auth" />
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            style={{
              background: '#FFFFFF0F',
              border: 'none',
              borderRadius: 'var(--radius-md, 8px)',
              color: 'var(--text-secondary, #CBD5E1)',
              width: '32px',
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              padding: 0
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Modal Header */}
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <h2
            id="auth-modal-title"
            style={{
              fontSize: '22px',
              fontWeight: 700,
              color: 'var(--text-primary, #FFFFFF)',
              margin: '0 0 6px 0',
              fontFamily: 'var(--font-display, 42dot Sans, sans-serif)'
            }}
          >
            {mode === 'login'
              ? t('auth.login.title')
              : mode === 'signup'
              ? t('auth.signup.title')
              : t('auth.forgot.title')}
          </h2>
          <p style={{ color: 'var(--text-tertiary, #94A3B8)', fontSize: '13px', margin: 0 }}>
            {mode === 'login'
              ? t('auth.login.subtitle')
              : mode === 'signup'
              ? t('auth.signup.subtitle')
              : t('auth.forgot.subtitle')}
          </p>
        </div>

        {/* Alerts */}
        {errorMsg && (
          <div
            role="alert"
            style={{
              background: '#EF44441F',
              border: '1px solid var(--accent-red, #EF4444)',
              borderRadius: 'var(--radius-md, 8px)',
              padding: '10px 14px',
              marginBottom: '16px',
              color: '#FCA5A5',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div
            role="alert"
            style={{
              background: '#10B9811F',
              border: '1px solid var(--accent-green, #10B981)',
              borderRadius: 'var(--radius-md, 8px)',
              padding: '10px 14px',
              marginBottom: '16px',
              color: '#6EE7B7',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <span>{successMsg}</span>
          </div>
        )}

        {/* ---------------- LOGIN MODE ---------------- */}
        {mode === 'login' && (
          <form onSubmit={handleSubmitLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label
                htmlFor="modal-login-email"
                style={{
                  display: 'block',
                  fontSize: '13px',
                  fontWeight: 600,
                  color: 'var(--text-secondary, #CBD5E1)',
                  marginBottom: '6px'
                }}
              >
                {t('auth.login.email')}
              </label>
              <input
                ref={firstInputRef}
                id="modal-login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t('auth.login.emailPlaceholder')}
                required
                style={{
                  width: '100%',
                  height: '48px',
                  background: 'var(--bg-surface-raised, #1A1D2A)',
                  border: '1px solid var(--border-default, #FFFFFF26)',
                  borderRadius: 'var(--radius-md, 8px)',
                  color: 'var(--text-primary, #FFFFFF)',
                  padding: '0 14px',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            <div>
              <label
                htmlFor="modal-login-password"
                style={{
                  display: 'block',
                  fontSize: '13px',
                  fontWeight: 600,
                  color: 'var(--text-secondary, #CBD5E1)',
                  marginBottom: '6px'
                }}
              >
                {t('auth.login.password')}
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="modal-login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t('auth.login.passwordPlaceholder')}
                  required
                  style={{
                    width: '100%',
                    height: '48px',
                    background: 'var(--bg-surface-raised, #1A1D2A)',
                    border: '1px solid var(--border-default, #FFFFFF26)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: 'var(--text-primary, #FFFFFF)',
                    padding: '0 44px 0 14px',
                    fontSize: '14px',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? t('auth.password.hide') : t('auth.password.show')}
                  style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-tertiary, #94A3B8)',
                    cursor: 'pointer',
                    padding: '4px'
                  }}
                >
                  {showPassword ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  id="modal-remember-email"
                  type="checkbox"
                  checked={rememberEmail}
                  onChange={(e) => setRememberEmail(e.target.checked)}
                  style={{ width: '16px', height: '16px', accentColor: 'var(--primary-600, #9333EA)' }}
                />
                <label htmlFor="modal-remember-email" style={{ fontSize: '13px', color: 'var(--text-secondary, #CBD5E1)', cursor: 'pointer' }}>
                  {t('auth.login.rememberEmail')}
                </label>
              </div>
              <button
                type="button"
                onClick={() => setMode('forgot')}
                style={{ background: 'none', border: 'none', color: 'var(--text-tertiary, #94A3B8)', fontSize: '13px', cursor: 'pointer' }}
              >
                {t('auth.login.forgotPassword')}
              </button>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                width: '100%',
                height: '50px',
                background: 'var(--primary-600, #9333EA)',
                border: 'none',
                borderRadius: 'var(--radius-md, 8px)',
                color: '#FFFFFF',
                fontSize: '15px',
                fontWeight: 700,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                marginTop: '4px'
              }}
            >
              {isSubmitting ? t('auth.login.loading') : t('auth.login.submit')}
            </button>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', fontSize: '13px', marginTop: '12px' }}>
              <span style={{ color: 'var(--text-tertiary, #94A3B8)' }}>{t('auth.signup.existingPrompt')}</span>
              <button
                type="button"
                onClick={() => setMode('signup')}
                style={{ color: 'var(--primary-400, #C084FC)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}
              >
                {t('auth.signup.title')}
              </button>
            </div>
          </form>
        )}

        {/* ---------------- SIGNUP MODE ---------------- */}
        {mode === 'signup' && (
          <form onSubmit={handleSubmitSignup} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label
                htmlFor="modal-signup-email"
                style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
              >
                {t('auth.signup.email')} *
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  ref={firstInputRef}
                  id="modal-signup-email"
                  type="email"
                  value={email}
                  onChange={(e) => handleEmailChange(e.target.value)}
                  placeholder={t('auth.signup.emailPlaceholder')}
                  required
                  style={{
                    flex: 1,
                    height: '48px',
                    background: 'var(--bg-surface-raised, #1A1D2A)',
                    border: '1px solid var(--border-default, #FFFFFF26)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: 'var(--text-primary, #FFFFFF)',
                    padding: '0 14px',
                    fontSize: '14px',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
                <button
                  type="button"
                  onClick={handleRequestSignupVerification}
                  disabled={isVerifyingEmail || emailVerified}
                  style={{
                    minWidth: '95px',
                    height: '48px',
                    background: emailVerified
                      ? '#10B98133'
                      : 'var(--bg-surface-raised, #1C2233)',
                    border: emailVerified
                      ? '1px solid var(--accent-green, #10B981)'
                      : '1px solid var(--border-strong, #FFFFFF40)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: emailVerified ? '#10B981' : 'var(--text-primary, #FFFFFF)',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: isVerifyingEmail || emailVerified ? 'default' : 'pointer'
                  }}
                >
                  {emailVerified
                    ? t('auth.signup.emailVerified')
                    : isVerifyingEmail
                    ? t('auth.signup.emailSending')
                    : t('auth.signup.emailVerify')}
                </button>
              </div>
              {emailStatusMsg && (
                <p style={{ fontSize: '12px', marginTop: '6px', color: emailVerified ? '#10B981' : 'var(--primary-400, #C084FC)' }}>
                  {emailStatusMsg}
                </p>
              )}

              {/* Code confirmation inline */}
              {emailCodeSent && !emailVerified && (
                <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                  <input
                    type="text"
                    value={verificationCode}
                    onChange={(e) => setVerificationCode(e.target.value)}
                    placeholder={t('auth.signup.enterCodePlaceholder')}
                    style={{
                      flex: 1,
                      height: '44px',
                      background: 'var(--bg-surface-raised, #1A1D2A)',
                      border: '1px solid var(--primary-500, #A855F7)',
                      borderRadius: 'var(--radius-md, 8px)',
                      color: 'var(--text-primary, #FFFFFF)',
                      padding: '0 12px',
                      fontSize: '13px'
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleConfirmSignupCode}
                    disabled={isConfirmingEmailCode}
                    style={{
                      padding: '0 14px',
                      height: '44px',
                      background: 'var(--primary-600, #9333EA)',
                      border: 'none',
                      borderRadius: 'var(--radius-md, 8px)',
                      color: '#FFFFFF',
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    {isConfirmingEmailCode ? t('auth.forgot.verifying') : t('auth.signup.confirmCode')}
                  </button>
                </div>
              )}
            </div>

            <div>
              <label
                htmlFor="modal-signup-password"
                style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
              >
                {t('auth.signup.password')} *
              </label>
              <input
                id="modal-signup-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('auth.signup.passwordPlaceholder')}
                required
                style={{
                  width: '100%',
                  height: '48px',
                  background: 'var(--bg-surface-raised, #1A1D2A)',
                  border: '1px solid var(--border-default, #FFFFFF26)',
                  borderRadius: 'var(--radius-md, 8px)',
                  color: 'var(--text-primary, #FFFFFF)',
                  padding: '0 14px',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  marginBottom: '8px'
                }}
              />
              <input
                id="modal-signup-confirm"
                type="password"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                placeholder={t('auth.signup.passwordConfirmPlaceholder')}
                required
                style={{
                  width: '100%',
                  height: '48px',
                  background: 'var(--bg-surface-raised, #1A1D2A)',
                  border: '1px solid var(--border-default, #FFFFFF26)',
                  borderRadius: 'var(--radius-md, 8px)',
                  color: 'var(--text-primary, #FFFFFF)',
                  padding: '0 14px',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
              <p style={{ fontSize: '11px', color: 'var(--text-tertiary, #94A3B8)', margin: '4px 0 0 0' }}>
                {t('auth.signup.passwordRule')}
              </p>
            </div>

            <div>
              <label
                htmlFor="modal-signup-nickname"
                style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
              >
                {t('auth.signup.nickname')}
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  id="modal-signup-nickname"
                  type="text"
                  value={nickname}
                  onChange={(e) => {
                    setNickname(e.target.value);
                    setNicknameChecked(false);
                    setNicknameStatusMsg(null);
                  }}
                  placeholder={t('auth.signup.nicknamePlaceholder')}
                  style={{
                    flex: 1,
                    height: '48px',
                    background: 'var(--bg-surface-raised, #1A1D2A)',
                    border: '1px solid var(--border-default, #FFFFFF26)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: 'var(--text-primary, #FFFFFF)',
                    padding: '0 14px',
                    fontSize: '14px',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
                <button
                  type="button"
                  onClick={handleCheckNickname}
                  disabled={isCheckingNickname}
                  style={{
                    minWidth: '95px',
                    height: '48px',
                    background: nicknameChecked
                      ? '#10B98133'
                      : 'var(--bg-surface-raised, #1C2233)',
                    border: nicknameChecked
                      ? '1px solid var(--accent-green, #10B981)'
                      : '1px solid var(--border-strong, #FFFFFF40)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: nicknameChecked ? '#10B981' : 'var(--text-primary, #FFFFFF)',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: isCheckingNickname ? 'default' : 'pointer'
                  }}
                >
                  {isCheckingNickname
                    ? t('auth.signup.checkingHandle')
                    : nicknameChecked
                    ? t('auth.signup.nicknameAvailable')
                    : t('auth.signup.checkAvailability')}
                </button>
              </div>
              {nicknameStatusMsg && (
                <p style={{ fontSize: '12px', marginTop: '6px', color: nicknameChecked ? '#10B981' : 'var(--primary-400, #C084FC)' }}>
                  {nicknameStatusMsg}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting || !emailVerified || !signupTicket}
              style={{
                width: '100%',
                height: '50px',
                background: (!emailVerified || !signupTicket || isSubmitting)
                  ? 'var(--bg-surface-raised, #1C2233)'
                  : 'var(--primary-600, #9333EA)',
                border: 'none',
                borderRadius: 'var(--radius-md, 8px)',
                color: (!emailVerified || !signupTicket) ? 'var(--text-tertiary, #94A3B8)' : '#FFFFFF',
                fontSize: '15px',
                fontWeight: 700,
                cursor: (!emailVerified || !signupTicket || isSubmitting) ? 'not-allowed' : 'pointer',
                marginTop: '4px'
              }}
            >
              {isSubmitting ? t('auth.signup.emailSending') : t('auth.signup.submit')}
            </button>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', fontSize: '13px', marginTop: '12px' }}>
              <span style={{ color: 'var(--text-tertiary, #94A3B8)' }}>{t('auth.signup.existingPrompt')}</span>
              <button
                type="button"
                onClick={() => setMode('login')}
                style={{ color: 'var(--primary-400, #C084FC)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}
              >
                {t('auth.signup.loginLink')}
              </button>
            </div>
          </form>
        )}

        {/* ---------------- FORGOT PASSWORD MODE ---------------- */}
        {mode === 'forgot' && (
          <form onSubmit={handleSubmitPasswordReset} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label
                htmlFor="modal-reset-email"
                style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
              >
                {t('auth.forgot.email')}
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  ref={firstInputRef}
                  id="modal-reset-email"
                  type="email"
                  value={email}
                  onChange={(e) => handleEmailChange(e.target.value)}
                  placeholder={t('auth.forgot.emailPlaceholder')}
                  required
                  disabled={resetCodeVerified}
                  style={{
                    flex: 1,
                    height: '48px',
                    background: 'var(--bg-surface-raised, #1A1D2A)',
                    border: '1px solid var(--border-default, #FFFFFF26)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: 'var(--text-primary, #FFFFFF)',
                    padding: '0 14px',
                    fontSize: '14px',
                    outline: 'none',
                    boxSizing: 'border-box'
                  }}
                />
                <button
                  type="button"
                  onClick={handleRequestResetCode}
                  disabled={isSendingResetCode || resetCodeVerified}
                  style={{
                    minWidth: '95px',
                    height: '48px',
                    background: resetCodeSent
                      ? '#10B98126'
                      : 'var(--bg-surface-raised, #1C2233)',
                    border: resetCodeSent
                      ? '1px solid var(--accent-green, #10B981)'
                      : '1px solid var(--border-strong, #FFFFFF40)',
                    borderRadius: 'var(--radius-md, 8px)',
                    color: resetCodeSent ? '#10B981' : 'var(--text-primary, #FFFFFF)',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: isSendingResetCode || resetCodeVerified ? 'default' : 'pointer'
                  }}
                >
                  {resetCodeSent
                    ? t('auth.signup.emailVerified')
                    : isSendingResetCode
                    ? t('auth.forgot.sending')
                    : t('auth.forgot.requestCode')}
                </button>
              </div>
            </div>

            {resetCodeSent && (
              <div>
                <label
                  htmlFor="modal-reset-code"
                  style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
                >
                  {t('auth.forgot.verificationCode')}
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    id="modal-reset-code"
                    type="text"
                    value={verificationCode}
                    onChange={(e) => setVerificationCode(e.target.value)}
                    placeholder={t('auth.forgot.verificationCodePlaceholder')}
                    required
                    disabled={resetCodeVerified}
                    style={{
                      flex: 1,
                      height: '48px',
                      background: 'var(--bg-surface-raised, #1A1D2A)',
                      border: '1px solid var(--border-default, #FFFFFF26)',
                      borderRadius: 'var(--radius-md, 8px)',
                      color: 'var(--text-primary, #FFFFFF)',
                      padding: '0 14px',
                      fontSize: '14px'
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleVerifyResetCode}
                    disabled={isVerifyingResetCode || resetCodeVerified}
                    style={{
                      minWidth: '95px',
                      height: '48px',
                      background: resetCodeVerified
                        ? '#10B98133'
                        : 'var(--primary-600, #9333EA)',
                      border: 'none',
                      borderRadius: 'var(--radius-md, 8px)',
                      color: '#FFFFFF',
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: isVerifyingResetCode || resetCodeVerified ? 'default' : 'pointer'
                    }}
                  >
                    {resetCodeVerified
                      ? t('auth.signup.emailVerified')
                      : isVerifyingResetCode
                      ? t('auth.forgot.verifying')
                      : t('auth.forgot.verifyCode')}
                  </button>
                </div>
              </div>
            )}

            {resetCodeVerified && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div>
                  <label
                    htmlFor="modal-new-password"
                    style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
                  >
                    {t('auth.forgot.newPassword')}
                  </label>
                  <input
                    id="modal-new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder={t('auth.forgot.newPasswordPlaceholder')}
                    required
                    style={{
                      width: '100%',
                      height: '48px',
                      background: 'var(--bg-surface-raised, #1A1D2A)',
                      border: '1px solid var(--border-default, #FFFFFF26)',
                      borderRadius: 'var(--radius-md, 8px)',
                      color: 'var(--text-primary, #FFFFFF)',
                      padding: '0 14px',
                      fontSize: '14px',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>
                <div>
                  <label
                    htmlFor="modal-new-password-confirm"
                    style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary, #CBD5E1)', marginBottom: '6px' }}
                  >
                    {t('auth.forgot.newPasswordConfirm')}
                  </label>
                  <input
                    id="modal-new-password-confirm"
                    type="password"
                    value={newPasswordConfirm}
                    onChange={(e) => setNewPasswordConfirm(e.target.value)}
                    placeholder={t('auth.forgot.newPasswordConfirmPlaceholder')}
                    required
                    style={{
                      width: '100%',
                      height: '48px',
                      background: 'var(--bg-surface-raised, #1A1D2A)',
                      border: '1px solid var(--border-default, #FFFFFF26)',
                      borderRadius: 'var(--radius-md, 8px)',
                      color: 'var(--text-primary, #FFFFFF)',
                      padding: '0 14px',
                      fontSize: '14px',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting || !resetCodeVerified || !resetTicket}
              style={{
                width: '100%',
                height: '50px',
                background: (!resetCodeVerified || !resetTicket || isSubmitting)
                  ? 'var(--bg-surface-raised, #1C2233)'
                  : 'var(--primary-600, #9333EA)',
                border: 'none',
                borderRadius: 'var(--radius-md, 8px)',
                color: (!resetCodeVerified || !resetTicket) ? 'var(--text-tertiary, #94A3B8)' : '#FFFFFF',
                fontSize: '15px',
                fontWeight: 700,
                cursor: (!resetCodeVerified || !resetTicket || isSubmitting) ? 'not-allowed' : 'pointer',
                marginTop: '4px'
              }}
            >
              {isSubmitting ? t('auth.forgot.completing') : t('auth.forgot.submit')}
            </button>

            <div style={{ display: 'flex', justifyContent: 'center', fontSize: '13px', marginTop: '12px' }}>
              <button
                type="button"
                onClick={() => setMode('login')}
                style={{ color: 'var(--primary-400, #C084FC)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}
              >
                ← {t('auth.login.title')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
