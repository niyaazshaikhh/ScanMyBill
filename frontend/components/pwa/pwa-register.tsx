'use client';

import { useEffect } from 'react';

export function PWARegister() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!('serviceWorker' in navigator)) return;
    if (!window.isSecureContext) return;

    void navigator.serviceWorker.register('/sw.js').catch(() => {
      // Non-blocking: app should work even if service worker registration fails.
    });
  }, []);

  return null;
}
