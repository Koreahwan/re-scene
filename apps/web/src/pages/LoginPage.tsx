import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../i18n/LocaleProvider';
import { getLocalizedErrorMessage } from '../utils/apiErrors';
import '../styles/auth.css';
import { authInputModality } from '../components/authInputModality';
import { authReturnDestination } from '../utils/navigation';

interface LoginPageProps {
  navigate: (path: string) => void;
}

const REMEMBER_EMAIL_KEY = 'rescene.rememberedEmail';

export const LoginPage: React.FC<LoginPageProps> = ({ navigate }) => {
  const { login, demoAccount } = useAuth();
  const { t } = useLocale();

  const [email, setEmail] = useState<string>(() => {
    try {
      return localStorage.getItem(REMEMBER_EMAIL_KEY) || '';
    } catch {
      return '';
    }
  });
  const [password, setPassword] = useState<string>('');
  const [rememberEmail, setRememberEmail] = useState<boolean>(() => {
    try {
      return !!localStorage.getItem(REMEMBER_EMAIL_KEY);
    } catch {
      return false;
    }
  });
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (demoAccount.enabled) {
      setEmail(demoAccount.email || '');
      setPassword(demoAccount.password || '');
      setRememberEmail(false);
    }
  }, [demoAccount]);

  const handleRememberEmailChange = (checked: boolean) => {
    setRememberEmail(checked);
    try {
      if (!checked) {
        localStorage.removeItem(REMEMBER_EMAIL_KEY);
      } else if (email) {
        localStorage.setItem(REMEMBER_EMAIL_KEY, email.trim());
      }
    } catch (err) {
      console.warn('Unable to access localStorage for remembered email:', err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password || isSubmitting) return;

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
      navigate(authReturnDestination());
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section {...authInputModality} className="auth-page auth-page--login" data-node-id="553:15293" data-layer="로그인">
      <div className="auth-panel auth-panel--login">
        <h1>LOG-IN</h1>

        {demoAccount.enabled && (
          <p className="auth-demo-notice" role="note">
            Your demo login is already filled in. No sign-up or password recovery needed.
            This account is shared: reviews and comments are public. Do not enter personal information.
          </p>
        )}

        {errorMsg && (
          <p className="auth-message" role="alert">
            {errorMsg}
          </p>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="auth-login-fields">
            <input
              id="login-email"
              className="auth-input"
              type="email"
              aria-label="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              required
              autoComplete="email"
              disabled={isSubmitting}
            />
            <input
              id="login-password"
              className="auth-input"
              type="password"
              aria-label="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              autoComplete="current-password"
              disabled={isSubmitting}
            />
            {!demoAccount.enabled && <label className="auth-remember">
              <input
                type="checkbox"
                checked={rememberEmail}
                onChange={(e) => handleRememberEmailChange(e.target.checked)}
                disabled={isSubmitting}
              />
              <span>Remember email</span>
            </label>}
          </div>

          <button
            type="submit"
            className="auth-button"
            disabled={isSubmitting || !email.trim() || !password}
          >
            {isSubmitting ? 'Logging in…' : 'LOG-IN'}
          </button>
        </form>

        {!demoAccount.enabled && <div className="auth-links">
          <button
            type="button"
            className="auth-link"
            onClick={() => navigate(`/signup?next=${encodeURIComponent(authReturnDestination())}`)}
          >
            SIGN-UP
          </button>
          <hr />
          <button
            type="button"
            className="auth-link"
            onClick={() => navigate(`/forgot-password?next=${encodeURIComponent(authReturnDestination())}`)}
          >
            Forgot Password?
          </button>
        </div>}
      </div>
    </section>
  );
};
