import type { AuthUser } from '@/lib/auth';
import { getAuthToken, getAuthUser, isAuthTokenExpired, setAuthSession } from '@/lib/auth';
import { showAppErrorPopup } from '@/lib/app-popup';
import { emitSessionTimeout } from '@/lib/session-timeout';

const DEFAULT_LOCAL_API_BASE = 'http://localhost:8000/api/v1';

function isLocalhost(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1';
}

function shouldUseLocalFallback(configuredBase: string): boolean {
  if (typeof window === 'undefined') return false;
  if (!isLocalhost(window.location.hostname.toLowerCase())) return false;
  if (!configuredBase) return true;

  try {
    const parsed = new URL(configuredBase);
    return parsed.hostname.toLowerCase() === 'scanmybill.xyz';
  } catch {
    return false;
  }
}

function resolveApiBase(): string {
  const configuredBase = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  if (shouldUseLocalFallback(configuredBase)) {
    return DEFAULT_LOCAL_API_BASE;
  }
  return configuredBase || DEFAULT_LOCAL_API_BASE;
}

type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  auth?: boolean;
  isFormData?: boolean;
  responseType?: 'json' | 'blob';
};

type RefreshResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function formatValidationErrors(detail: unknown): string | null {
  if (!Array.isArray(detail)) {
    return null;
  }

  const messages = detail
    .map((entry) => {
      if (!isRecord(entry)) {
        return null;
      }

      const rawMessage = entry.msg;
      if (typeof rawMessage !== 'string' || !rawMessage.trim()) {
        return null;
      }

      const rawLoc = entry.loc;
      if (!Array.isArray(rawLoc)) {
        return rawMessage.trim();
      }

      const location = rawLoc
        .filter((segment): segment is string | number => typeof segment === 'string' || typeof segment === 'number')
        .map((segment) => String(segment))
        .filter((segment) => segment !== 'body' && segment !== 'query' && segment !== 'path')
        .join('.');

      if (!location) {
        return rawMessage.trim();
      }

      return `${location}: ${rawMessage.trim()}`;
    })
    .filter((message): message is string => Boolean(message));

  if (!messages.length) {
    return null;
  }

  return messages.join('; ');
}

function extractApiErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  const detail = payload.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }

  const nestedError = payload.error;
  if (isRecord(nestedError)) {
    const nestedMessage = nestedError.message;
    if (typeof nestedMessage === 'string' && nestedMessage.trim()) {
      return nestedMessage.trim();
    }
  }

  const validationMessage = formatValidationErrors(detail);
  if (validationMessage) {
    return validationMessage;
  }

  const message = payload.message;
  if (typeof message === 'string' && message.trim()) {
    return message.trim();
  }

  const error = payload.error;
  if (typeof error === 'string' && error.trim()) {
    return error.trim();
  }

  return fallback;
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const apiBase = resolveApiBase();
    const res = await fetch(`${apiBase}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) return false;

    const data = (await res.json()) as RefreshResponse;
    if (!data?.access_token || !data?.user) return false;
    setAuthSession(data.access_token, data.user);
    return true;
  } catch {
    return false;
  }
}

function applyRotatedAccessToken(response: Response) {
  const rotatedToken = response.headers.get('X-Access-Token');
  if (!rotatedToken) return;

  const currentUser = getAuthUser();
  if (!currentUser) return;

  setAuthSession(rotatedToken, currentUser);
}

export async function apiRequest<T = unknown>(
  path: string,
  options: ApiOptions = {}
): Promise<T> {
  const sessionTimeoutMessage = 'Session timed out. Please log in again.';

  const {
    method = 'GET',
    body,
    auth = true,
    isFormData = false,
    responseType = 'json'
  } = options;

  const executeRequest = async (tokenOverride?: string | null) => {
    const apiBase = resolveApiBase();
    const headers: HeadersInit = {};
    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }

    if (auth) {
      const token = tokenOverride ?? getAuthToken();
      if (!token) {
        emitSessionTimeout(sessionTimeoutMessage);
        throw new Error(sessionTimeoutMessage);
      }
      headers.Authorization = `Bearer ${token}`;
    }

    const url = `${apiBase}${path}`;
    try {
      return await fetch(url, {
        method,
        headers,
        credentials: 'include',
        body:
          body === undefined
            ? undefined
            : isFormData
            ? (body as FormData)
            : JSON.stringify(body)
      });
    } catch (error) {
      const activeToken = tokenOverride ?? getAuthToken();
      if (auth && isAuthTokenExpired(activeToken)) {
        emitSessionTimeout(sessionTimeoutMessage);
        throw new Error(sessionTimeoutMessage);
      }
      const mixedContentHint =
        typeof window !== 'undefined'
        && window.location.protocol === 'https:'
        && apiBase.startsWith('http://')
          ? ' Mixed-content blocked: frontend is HTTPS but API URL is HTTP.'
          : '';
      const reason = error instanceof Error ? error.message : 'Failed to fetch';
      const message = `Network error: Unable to reach API at ${url}. ${reason}.${mixedContentHint}`;
      showAppErrorPopup(message, 'Network Error');
      throw new Error(message);
    }
  };

  let res = await executeRequest();
  applyRotatedAccessToken(res);

  if (!res.ok) {
    if (auth && res.status === 401) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        res = await executeRequest(getAuthToken());
        applyRotatedAccessToken(res);
      } else {
        emitSessionTimeout(sessionTimeoutMessage);
        throw new Error(sessionTimeoutMessage);
      }
    }
  }

  if (!res.ok) {

    let message = `API Error (${res.status})`;
    const contentType = (res.headers.get('content-type') || '').toLowerCase();
    try {
      if (contentType.includes('application/json')) {
        const json = await res.json();
        message = extractApiErrorMessage(json, message);
      } else {
        const text = await res.text();
        if (text.trim()) {
          message = text.trim();
        }
      }
    } catch {
      // Ignore JSON parsing errors for non-JSON responses.
    }
    showAppErrorPopup(message, 'Request Failed');
    throw new Error(message);
  }

  if (responseType === 'blob') {
    return (await res.blob()) as T;
  }

  if (res.status === 204) {
    return {} as T;
  }

  return (await res.json()) as T;
}

export function getApiBaseUrl() {
  return resolveApiBase();
}
