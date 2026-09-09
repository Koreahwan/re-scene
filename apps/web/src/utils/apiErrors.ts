/**
 * Reframe V7 Stable Localized Error Code Mapping
 * Enforces zero raw backend English message leakage in normal UI.
 */

export const ERROR_CODE_TO_MESSAGE_KEY: Record<string, string> = {
  AUTH_INVALID_CREDENTIALS: 'auth.error.invalidCredentials',
  AUTH_ACCOUNT_LOCKED: 'auth.error.accountLocked',
  AUTH_CODE_INVALID: 'auth.error.codeInvalid',
  AUTH_CODE_EXPIRED: 'auth.error.codeInvalid',
  AUTH_RATE_LIMITED: 'auth.error.rateLimited',
  AUTH_EMAIL_NOT_VERIFIED: 'auth.error.emailNotVerified',
  AUTH_HANDLE_INVALID: 'auth.error.handleInvalid',
  AUTH_HANDLE_UNAVAILABLE: 'auth.error.handleUnavailable',
  AUTH_CHALLENGE_STORE_UNAVAILABLE: 'auth.error.challengeStoreUnavailable',
  AUTH_EMAIL_UNAVAILABLE: 'auth.error.emailUnavailable',
  AUTH_DELIVERY_DISABLED: 'auth.error.deliveryDisabled',
  AUTH_REQUIRED: 'auth.error.invalidCredentials',
  INVALID_REQUEST: 'auth.error.generic',
  NOT_FOUND: 'common.notFound'
};

export function getLocalizedErrorMessage(
  error: any,
  t: (key: string, params?: Record<string, string | number>) => string
): string {
  if (!error) return t('auth.error.generic');

  const code = error.code || error.error?.code;
  if (code && typeof code === 'string' && ERROR_CODE_TO_MESSAGE_KEY[code]) {
    return t(ERROR_CODE_TO_MESSAGE_KEY[code]);
  }

  // Strictly return localized generic error (never leak raw unlocalized messages)
  return t('auth.error.generic');
}
