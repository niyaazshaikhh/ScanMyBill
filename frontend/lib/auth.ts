const TOKEN_KEY = 'scanmybill_token';
const USER_KEY = 'scanmybill_user';

export type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'user';
  subscription_plan?: 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';
  subscription_status?: 'ACTIVE' | 'CANCELLED' | 'EXPIRED';
};

export function setAuthSession(token: string, user: AuthUser) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  document.cookie = `token=${token}; path=/; max-age=604800; SameSite=Lax`;
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

export function clearAuthSession() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  document.cookie = 'token=; path=/; max-age=0; SameSite=Lax';
}

export function logoutToLanding() {
  if (typeof window === 'undefined') return;
  clearAuthSession();
  if (window.location.pathname !== '/') {
    window.location.replace('/');
  }
}
