import { useEffect, useRef } from 'react';
import { BEFORE_NAVIGATE, NavigationDetail } from './navigation';

export function useUnsavedChanges(dirty: boolean, preserveForLogin?: () => void) {
  const preserve = useRef(preserveForLogin);
  preserve.current = preserveForLogin;
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const beforeNavigate = (event: Event) => {
      if (event.defaultPrevented) return;
      const path = (event as CustomEvent<NavigationDetail>).detail.path;
      if (/^\/(login|signup)(\?|$)/.test(path) && preserve.current) {
        preserve.current();
        return;
      }
      if (!window.confirm('Discard your unsaved changes?')) event.preventDefault();
    };
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener(BEFORE_NAVIGATE, beforeNavigate);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      window.removeEventListener(BEFORE_NAVIGATE, beforeNavigate);
    };
  }, [dirty]);
}
