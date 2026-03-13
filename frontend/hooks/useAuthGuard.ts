'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { clearAuthSession, getAuthToken } from '@/lib/auth';

const IDLE_ACTIVITY_KEY = 'scanmybill_last_activity_at';
const DEFAULT_IDLE_MINUTES = 30;
const ACTIVITY_WRITE_THROTTLE_MS = 10_000;

function getIdleTimeoutMs() {
  const parsed = Number(
    process.env.NEXT_PUBLIC_SESSION_IDLE_TIMEOUT_MINUTES
      ?? process.env.NEXT_PUBLIC_IDLE_TIMEOUT_MINUTES
      ?? DEFAULT_IDLE_MINUTES
  );
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_IDLE_MINUTES * 60 * 1000;
  }
  return parsed * 60 * 1000;
}

export function useAuthGuard() {
  const router = useRouter();

  useEffect(() => {
    let idleTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let lastActivityWriteAt = 0;
    const idleTimeoutMs = getIdleTimeoutMs();
    const logoutToLanding = () => {
      clearAuthSession();
      router.replace('/');
    };

    const scheduleIdleLogout = () => {
      if (!getAuthToken()) {
        logoutToLanding();
        return;
      }

      const lastRaw = localStorage.getItem(IDLE_ACTIVITY_KEY);
      const lastActivityAt = Number(lastRaw || Date.now());
      const elapsed = Date.now() - (Number.isFinite(lastActivityAt) ? lastActivityAt : Date.now());
      const remaining = idleTimeoutMs - elapsed;

      if (idleTimeoutId) {
        clearTimeout(idleTimeoutId);
      }

      if (remaining <= 0) {
        logoutToLanding();
        return;
      }

      idleTimeoutId = setTimeout(() => {
        logoutToLanding();
      }, remaining);
    };

    const markActivity = () => {
      const now = Date.now();
      if (now - lastActivityWriteAt < ACTIVITY_WRITE_THROTTLE_MS) {
        return;
      }
      lastActivityWriteAt = now;
      localStorage.setItem(IDLE_ACTIVITY_KEY, String(now));
      scheduleIdleLogout();
    };

    if (!getAuthToken()) {
      logoutToLanding();
      return;
    }

    if (!localStorage.getItem(IDLE_ACTIVITY_KEY)) {
      localStorage.setItem(IDLE_ACTIVITY_KEY, String(Date.now()));
    }
    scheduleIdleLogout();

    const activityEvents: Array<keyof WindowEventMap> = [
      'mousemove',
      'mousedown',
      'keydown',
      'scroll',
      'touchstart',
      'click',
    ];

    activityEvents.forEach((eventName) => {
      window.addEventListener(eventName, markActivity, { passive: true });
    });

    const onStorage = () => {
      scheduleIdleLogout();
    };
    window.addEventListener('storage', onStorage);

    return () => {
      if (idleTimeoutId) {
        clearTimeout(idleTimeoutId);
      }
      activityEvents.forEach((eventName) => {
        window.removeEventListener(eventName, markActivity);
      });
      window.removeEventListener('storage', onStorage);
    };
  }, [router]);
}
