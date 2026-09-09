/** Only in-app destinations may be used after authentication. */
export function safeReturnPath(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u001f]/.test(value)) return '/films';
  const url = new URL(value, 'https://rescene.invalid');
  if (url.origin !== 'https://rescene.invalid' || /^\/(login|signup|forgot-password|reset-password)(\/|$)/.test(url.pathname)) return '/films';
  return url.pathname + url.search + url.hash;
}

export function loginDestination(returnTo = window.location.pathname + window.location.search): string {
  return `/login?next=${encodeURIComponent(safeReturnPath(returnTo))}`;
}

export function authReturnDestination(): string {
  return safeReturnPath(new URLSearchParams(window.location.search).get('next'));
}

export const BEFORE_NAVIGATE = 'rescene:before-navigate';
export interface NavigationDetail { path: string }
export function confirmNavigation(path: string): boolean {
  return window.dispatchEvent(new CustomEvent<NavigationDetail>(BEFORE_NAVIGATE, {
    cancelable: true, detail: { path },
  }));
}
