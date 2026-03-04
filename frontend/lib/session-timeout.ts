export const SESSION_TIMEOUT_EVENT = 'scanmybill:session-timeout';

export type SessionTimeoutDetail = {
  message: string;
};

let lastSessionTimeoutAt = 0;
const EVENT_THROTTLE_MS = 3000;

export function emitSessionTimeout(message = 'Session timed out. Please log in again.') {
  if (typeof window === 'undefined') return;
  const now = Date.now();
  if (now - lastSessionTimeoutAt < EVENT_THROTTLE_MS) return;
  lastSessionTimeoutAt = now;
  window.dispatchEvent(
    new CustomEvent<SessionTimeoutDetail>(SESSION_TIMEOUT_EVENT, {
      detail: { message },
    }),
  );
}
