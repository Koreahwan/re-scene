import React, { useState, useRef } from 'react';
import { apiClient } from '../services/apiClient';
import { useLocale } from '../i18n/LocaleProvider';
import { getLocalizedErrorMessage } from '../utils/apiErrors';
import '../styles/auth.css';
import { authInputModality } from '../components/authInputModality';

export const ForgotPasswordPage: React.FC<{ navigate: (path: string) => void }> = ({ navigate }) => {
  const { t } = useLocale();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [requested, setRequested] = useState(false);
  const [ticket, setTicket] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [complete, setComplete] = useState(false);
  const reqGen = useRef(0);

  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); } catch (err) { setError(getLocalizedErrorMessage(err, t)); }
    finally { setBusy(false); }
  };
  const requestCode = () => {
    const cur = ++reqGen.current;
    perform(async () => {
      await apiClient.auth.requestPasswordReset(email.trim());
      if (cur !== reqGen.current) return;
      setRequested(true); setCode(''); setTicket('');
      setMessage('If an account exists with this email, a recovery code has been sent.');
    });
  };
  const verifyCode = () => {
    const cur = ++reqGen.current;
    perform(async () => {
      const result = await apiClient.auth.verifyPasswordReset(email.trim(), code.trim());
      if (cur !== reqGen.current) return;
      if (!result.data.valid || !result.data.password_reset_ticket) throw new Error('The recovery code could not be verified.');
      setTicket(result.data.password_reset_ticket);
      setCode(''); setMessage('Email verified. Choose a new password.');
    });
  };
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ticket || busy || password.length < 8 || password !== confirmation) return;
    const cur = ++reqGen.current;
    void perform(async () => {
      const result = await apiClient.auth.completePasswordReset(email.trim(), ticket, password);
      if (cur !== reqGen.current) return;
      if (!result.data.updated) throw new Error('Your password could not be updated.');
      setTicket(''); setPassword(''); setConfirmation(''); setComplete(true);
      setMessage('Your password has been updated. Sign in with your new password.');
    });
  };

  return <section {...authInputModality} className="auth-page" data-node-id="553:15358">
    <div className="auth-panel">
      <h1>Forgot Password?</h1>
      {error && <p className="auth-message" role="alert">{error}</p>}
      {message && <p className="auth-message" role="status">{message}</p>}
      {complete ? <button className="auth-button" onClick={() => navigate('/login')}>LOG-IN</button> :
        <form className="auth-form" onSubmit={submit}>
          <label className="auth-field" htmlFor="recovery-email">Email
            <div className="auth-row">
              <input className="auth-input" id="recovery-email" type="email" autoComplete="email" placeholder="Enter your email" required value={email} disabled={busy || !!ticket}
                onChange={e => { reqGen.current += 1; setEmail(e.target.value); setRequested(false); setCode(''); setTicket(''); setError(''); setMessage(''); }} />
              <button className="auth-button" type="button" disabled={busy || !!ticket || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())} onClick={requestCode}>{requested ? 'Resend' : 'Send code'}</button>
            </div>
          </label>
          {!ticket && <label className="auth-field" htmlFor="recovery-code">Verification code
            <div className="auth-row">
              <input className="auth-input" id="recovery-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} placeholder="Enter verification code" value={code} disabled={busy || !requested} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} />
              <button className="auth-button" type="button" disabled={busy || !requested || !/^\d{6}$/.test(code)} onClick={verifyCode}>Verify</button>
            </div>
          </label>}
          {ticket && <>
            <label className="auth-field" htmlFor="recovery-password">New password
              <input className="auth-input" id="recovery-password" type="password" autoComplete="new-password" minLength={8} required disabled={busy} value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" />
            </label>
            <label className="auth-field" htmlFor="recovery-confirm">Confirm new password
              <input className="auth-input" id="recovery-confirm" type="password" autoComplete="new-password" minLength={8} required disabled={busy} value={confirmation} onChange={e => setConfirmation(e.target.value)} placeholder="Repeat your new password" />
            </label>
            {confirmation && confirmation !== password && <p className="auth-message" role="alert">Passwords do not match.</p>}
          </>}
          <button className="auth-button" type="submit" disabled={busy || !ticket || password.length < 8 || password !== confirmation}>{busy ? 'Please wait…' : 'Reset password'}</button>
        </form>}
      {!complete && <div className="auth-links"><button className="auth-link" onClick={() => navigate('/login')}>Back to log-in</button></div>}
    </div>
  </section>;
};
