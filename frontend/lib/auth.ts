import {
  normalizeSubscriptionStatus,
  resolveEffectiveSubscriptionPlan,
} from '@/lib/subscription-access';

const TOKEN_KEY = 'scanmybill_token';
const USER_KEY = 'scanmybill_user';
const IDLE_ACTIVITY_KEY = 'scanmybill_last_activity_at';
const TOKEN_COOKIE_KEY = 'token';
const SUBSCRIPTION_PLAN_COOKIE_KEY = 'subscription_plan';
const SUBSCRIPTION_STATUS_COOKIE_KEY = 'subscription_status';
const AUTH_COOKIE_MAX_AGE_SECONDS = 604800;

export type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'user';
  notifications_enabled?: boolean;
  subscription_plan?: 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';
  subscription_status?: 'ACTIVE' | 'CANCELLED' | 'EXPIRED';
  razorpay_subscription_id?: string | null;
  subscription_started_at?: string | null;
  subscription_expires_at?: string | null;
};

function setCookie(name: string, value: string, maxAgeSeconds = AUTH_COOKIE_MAX_AGE_SECONDS) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax`;
}

function clearCookie(name: string) {
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

function syncSubscriptionCookies(user: Pick<AuthUser, 'subscription_plan' | 'subscription_status'> | null) {
  const effectivePlan = resolveEffectiveSubscriptionPlan(user?.subscription_plan, user?.subscription_status);
  const normalizedStatus = normalizeSubscriptionStatus(user?.subscription_status);
  setCookie(SUBSCRIPTION_PLAN_COOKIE_KEY, effectivePlan);
  setCookie(SUBSCRIPTION_STATUS_COOKIE_KEY, normalizedStatus);
}

export function setAuthSession(token: string, user: AuthUser) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  localStorage.setItem(IDLE_ACTIVITY_KEY, String(Date.now()));
  setCookie(TOKEN_COOKIE_KEY, token);
  syncSubscriptionCookies(user);
}

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length < 2) return null;

  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const payload = atob(padded);
    return JSON.parse(payload) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function getAuthTokenExpiryMs(tokenInput?: string | null): number | null {
  const token = tokenInput ?? getAuthToken();
  if (!token) return null;

  const payload = decodeJwtPayload(token);
  if (!payload) return null;

  const expRaw = payload.exp;
  const expSeconds =
    typeof expRaw === 'number' ? expRaw : typeof expRaw === 'string' ? Number(expRaw) : NaN;

  if (!Number.isFinite(expSeconds)) return null;
  return expSeconds * 1000;
}

export function isAuthTokenExpired(tokenInput?: string | null): boolean {
  const expiryMs = getAuthTokenExpiryMs(tokenInput);
  if (!expiryMs) return true;
  return Date.now() >= expiryMs;
}

export function getAuthUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function updateAuthUser(updates: Partial<AuthUser>) {
  if (typeof window === 'undefined') return;
  const current = getAuthUser();
  if (!current) return;

  const merged: AuthUser = { ...current, ...updates };
  localStorage.setItem(USER_KEY, JSON.stringify(merged));
  syncSubscriptionCookies(merged);
}

export function clearAuthSession() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(IDLE_ACTIVITY_KEY);
  clearCookie(TOKEN_COOKIE_KEY);
  clearCookie(SUBSCRIPTION_PLAN_COOKIE_KEY);
  clearCookie(SUBSCRIPTION_STATUS_COOKIE_KEY);
}

export function logoutToLanding() {
  if (typeof window === 'undefined') return;
  clearAuthSession();
  if (window.location.pathname !== '/') {
    window.history.replaceState(null, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
  }
}
