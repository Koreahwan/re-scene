import React, { useState, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../i18n/LocaleProvider';
import { apiClient } from '../services/apiClient';
import { getLocalizedErrorMessage } from '../utils/apiErrors';
import '../styles/auth.css';
import { authInputModality } from '../components/authInputModality';
import { authReturnDestination, loginDestination } from '../utils/navigation';

interface SignupPageProps {
  navigate: (path: string) => void;
}

export const SignupPage: React.FC<SignupPageProps> = ({ navigate }) => {
  const { signup } = useAuth();
  const { t } = useLocale();

  const [email, setEmail] = useState<string>('');
  const [verificationCode, setVerificationCode] = useState<string>('');
  const [emailVerificationTicket, setEmailVerificationTicket] = useState<string>('');
  const [isVerifyingEmail, setIsVerifyingEmail] = useState<boolean>(false);
  const [isConfirmingCode, setIsConfirmingCode] = useState<boolean>(false);
  const [emailCodeSent, setEmailCodeSent] = useState<boolean>(false);
  const [emailVerified, setEmailVerified] = useState<boolean>(false);
  const [emailStatusMsg, setEmailStatusMsg] = useState<string | null>(null);

  const [password, setPassword] = useState<string>('');
  const [passwordConfirm, setPasswordConfirm] = useState<string>('');

  const [nickname, setNickname] = useState<string>('');
  const [isCheckingNickname, setIsCheckingNickname] = useState<boolean>(false);
  const [nicknameChecked, setNicknameChecked] = useState<boolean>(false);
  const [nicknameStatusMsg, setNicknameStatusMsg] = useState<string | null>(null);

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Request generation counters to prevent late race-condition overwrites
  const emailReqGen = useRef(0);
  const nicknameReqGen = useRef(0);

  const handleEmailChange = (newEmail: string) => {
    emailReqGen.current += 1;
    setEmail(newEmail);
    setEmailVerified(false);
    setEmailVerificationTicket('');
    setVerificationCode('');
    setEmailCodeSent(false);
    setEmailStatusMsg(null);
    setErrorMsg(null);
    setIsConfirmingCode(false);
    setIsVerifyingEmail(false);
  };

  const handleNicknameChange = (newNick: string) => {
    nicknameReqGen.current += 1;
    setNickname(newNick);
    setNicknameChecked(false);
    setNicknameStatusMsg(null);
    setErrorMsg(null);
  };

  const handleRequestEmailVerification = async () => {
    const cleanEmail = email.trim();
    if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setEmailStatusMsg('Please enter a valid email address.');
      return;
    }
    const curGen = ++emailReqGen.current;
    setIsVerifyingEmail(true);
    setEmailStatusMsg(null);
    setErrorMsg(null);

    try {
      await apiClient.auth.requestEmailVerification(cleanEmail);
      if (curGen !== emailReqGen.current) return;
      setEmailCodeSent(true);
      setEmailStatusMsg('Verification code sent. Please check your inbox.');
    } catch (err: any) {
      if (curGen !== emailReqGen.current) return;
      setEmailStatusMsg(getLocalizedErrorMessage(err, t));
    } finally {
      if (curGen === emailReqGen.current) {
        setIsVerifyingEmail(false);
      }
    }
  };

  const handleConfirmEmailCode = async () => {
    const cleanCode = verificationCode.trim();
    if (!cleanCode) return;
    const curGen = emailReqGen.current;
    setIsConfirmingCode(true);
    setEmailStatusMsg(null);
    setErrorMsg(null);

    try {
      const res = await apiClient.auth.confirmEmailVerification(email.trim(), cleanCode);
      if (curGen !== emailReqGen.current) return;
      setEmailVerified(true);
      setEmailVerificationTicket(res.data.email_verification_ticket);
      setEmailStatusMsg('Email verified successfully.');
    } catch (err: any) {
      if (curGen !== emailReqGen.current) return;
      setEmailStatusMsg(getLocalizedErrorMessage(err, t));
    } finally {
      if (curGen === emailReqGen.current) {
        setIsConfirmingCode(false);
      }
    }
  };

  const handleCheckNickname = async () => {
    const cleanNick = nickname.trim();
    if (!cleanNick || cleanNick.length < 2) {
      setNicknameStatusMsg('Nickname must be at least 2 characters long.');
      return;
    }
    const curGen = ++nicknameReqGen.current;
    setIsCheckingNickname(true);
    setNicknameStatusMsg('Checking availability…');
    setErrorMsg(null);

    try {
      const res = await apiClient.auth.checkHandleAvailability(cleanNick);
      if (curGen !== nicknameReqGen.current) return;
      if (res.data.available) {
        setNicknameChecked(true);
        setNicknameStatusMsg('Nickname is available.');
      } else {
        setNicknameChecked(false);
        setNicknameStatusMsg('This nickname is already taken.');
      }
    } catch (err: any) {
      if (curGen !== nicknameReqGen.current) return;
      setNicknameStatusMsg(getLocalizedErrorMessage(err, t));
    } finally {
      if (curGen === nicknameReqGen.current) {
        setIsCheckingNickname(false);
      }
    }
  };

  const isFormValid = Boolean(
    emailVerified &&
    emailVerificationTicket &&
    password &&
    password === passwordConfirm &&
    password.length >= 8 &&
    nicknameChecked &&
    nickname.trim()
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await signup(
        email.trim(),
        password,
        emailVerificationTicket,
        nickname.trim(),
        nickname.trim()
      );
      setSuccessMsg('Account created successfully!');
      navigate(authReturnDestination());
    } catch (err: any) {
      setErrorMsg(getLocalizedErrorMessage(err, t));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section {...authInputModality} className="auth-page" data-node-id="553:15320" data-layer="회원가입">
      <div className="auth-panel">
        <h1>SIGN-UP</h1>

        {errorMsg && (
          <p className="auth-message" role="alert">
            {errorMsg}
          </p>
        )}
        {successMsg && (
          <p className="auth-message" role="status" style={{ color: '#27AE60' }}>
            {successMsg}
          </p>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          {/* Email verification row */}
          <div className="auth-field">
            <label htmlFor="signup-email">Email</label>
            <div className="auth-row">
              <input
                id="signup-email"
                className="auth-input"
                type="email"
                value={email}
                onChange={(e) => handleEmailChange(e.target.value)}
                placeholder="Enter your email"
                required
                autoComplete="email"
                disabled={isVerifyingEmail || emailVerified}
              />
              <button
                type="button"
                className="auth-button"
                onClick={handleRequestEmailVerification}
                disabled={isVerifyingEmail || emailVerified || !email.trim()}
              >
                {isVerifyingEmail ? 'Sending…' : emailCodeSent ? 'Resend' : 'Send code'}
              </button>
            </div>
            {emailStatusMsg && (
              <p className="auth-message" role={emailVerified ? 'status' : 'alert'} style={{ color: emailVerified ? '#4C22F4' : undefined }}>
                {emailStatusMsg}
              </p>
            )}
          </div>

          {/* Verification Code row */}
          {emailCodeSent && !emailVerified && (
            <div className="auth-field">
              <label htmlFor="signup-code">Verification Code</label>
              <div className="auth-row">
                <input
                  id="signup-code"
                  className="auth-input"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="Enter 6-digit code"
                  disabled={isConfirmingCode}
                />
                <button
                  type="button"
                  className="auth-button"
                  onClick={handleConfirmEmailCode}
                  disabled={isConfirmingCode || verificationCode.trim().length < 6}
                >
                  {isConfirmingCode ? 'Verifying…' : 'Verify'}
                </button>
              </div>
            </div>
          )}

          {/* Password fields */}
          <div className="auth-field">
            <label htmlFor="signup-password">Password</label>
            <input
              id="signup-password"
              className="auth-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              required
              minLength={8}
              autoComplete="new-password"
            />
          </div>

          <div className="auth-field">
            <label htmlFor="signup-password-confirm">Confirm Password</label>
            <input
              id="signup-password-confirm"
              className="auth-input"
              type="password"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              placeholder="Repeat your password"
              required
              minLength={8}
              autoComplete="new-password"
            />
            {passwordConfirm && password !== passwordConfirm && (
              <p className="auth-message" role="alert">
                Passwords do not match.
              </p>
            )}
          </div>

          {/* Nickname row */}
          <div className="auth-field">
            <label htmlFor="signup-nickname">Nickname</label>
            <div className="auth-row">
              <input
                id="signup-nickname"
                className="auth-input"
                type="text"
                value={nickname}
                onChange={(e) => handleNicknameChange(e.target.value)}
                placeholder="Choose a nickname"
                required
                minLength={2}
                disabled={isCheckingNickname}
              />
              <button
                type="button"
                className="auth-button"
                onClick={handleCheckNickname}
                disabled={isCheckingNickname || nickname.trim().length < 2 || nicknameChecked}
              >
                {isCheckingNickname ? 'Checking…' : nicknameChecked ? 'Checked' : 'Check'}
              </button>
            </div>
            {nicknameStatusMsg && (
              <p className="auth-message" role={nicknameChecked ? 'status' : 'alert'} style={{ color: nicknameChecked ? '#4C22F4' : undefined }}>
                {nicknameStatusMsg}
              </p>
            )}
          </div>

          <button
            type="submit"
            className="auth-button"
            disabled={!isFormValid || isSubmitting}
          >
            {isSubmitting ? 'Creating account…' : 'SIGN-UP'}
          </button>
        </form>

        <div className="auth-links">
          <span style={{ color: '#898992', fontSize: 14 }}>Already have an account?</span>
          <button
            type="button"
            className="auth-link"
            onClick={() => navigate(loginDestination(authReturnDestination()))}
          >
            LOG-IN
          </button>
        </div>
      </div>
    </section>
  );
};
