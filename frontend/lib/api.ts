import type { AuthUser } from '@/lib/auth';
import { getAuthToken, getAuthUser, isAuthTokenExpired, setAuthSession } from '@/lib/auth';
import { showAppErrorPopup } from '@/lib/app-popup';
import { appendDashboardDebugRecord, getDebugModeEnabled } from '@/lib/debugging';
import { emitSessionTimeout } from '@/lib/session-timeout';

const DEFAULT_LOCAL_API_BASE = 'http://localhost:8000/api/v1';
const DEFAULT_PRODUCTION_API_BASE = 'https://api.scanmybill.xyz/api/v1';
const API_DEBUG_MAX_PAYLOAD_CHARS = 12_000;
const NODE_ENV = process.env.NODE_ENV || 'development';
const CONFIGURED_PUBLIC_API_URL = (process.env.NEXT_PUBLIC_API_URL || '').trim();

if (NODE_ENV === 'production' && !CONFIGURED_PUBLIC_API_URL) {
  throw new Error('NEXT_PUBLIC_API_URL must be defined in production build');
}

function resolveConfiguredApiBase(configuredBase: string): string {
  if (!configuredBase) return '';

  if (configuredBase.startsWith('/')) {
    if (typeof window === 'undefined') return configuredBase;
    return `${window.location.origin}${configuredBase}`;
  }
  return configuredBase;
}

function resolveApiBase(): string {
  const configuredBase = resolveConfiguredApiBase(CONFIGURED_PUBLIC_API_URL);
  if (configuredBase) {
    return configuredBase;
  }
  return NODE_ENV === 'development' ? DEFAULT_LOCAL_API_BASE : DEFAULT_PRODUCTION_API_BASE;
}

const API_BASE = resolveApiBase();

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

function shouldCaptureApiDebug(): boolean {
  if (typeof window === 'undefined') return false;
  return getDebugModeEnabled();
}

function toDebugPayload(value: unknown): unknown {
  if (value === undefined) {
    return null;
  }

  try {
    const serialized = JSON.stringify(value);
    if (serialized.length <= API_DEBUG_MAX_PAYLOAD_CHARS) {
      return value;
    }
    return {
      truncated: true,
      preview: `${serialized.slice(0, API_DEBUG_MAX_PAYLOAD_CHARS)}...`,
      original_chars: serialized.length,
    };
  } catch {
    return String(value);
  }
}

function toDebugHeaders(response: Response): Record<string, string> {
  const headers: Record<string, string> = {};
  response.headers.forEach((value, key) => {
    headers[key] = value;
  });
  return headers;
}

function appendApiDebugRecord(input: {
  level: 'info' | 'success' | 'warning' | 'error';
  method: string;
  path: string;
  message: string;
  status?: number;
  details?: unknown;
}) {
  if (!shouldCaptureApiDebug()) {
    return;
  }

  const statusLabel = typeof input.status === 'number' ? ` (${input.status})` : '';
  appendDashboardDebugRecord({
    level: input.level,
    source: 'api',
    title: `API ${input.method} ${input.path}${statusLabel}`,
    message: input.message,
    details: input.details,
  });
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
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

  const requestLabel = `${method} ${path}`;

  const executeRequest = async (tokenOverride?: string | null) => {
    const headers: HeadersInit = {};
    if (!isFormData) {
      headers['Content-Type'] = 'application/json';
    }

    if (auth) {
      const token = tokenOverride ?? getAuthToken();
      if (!token) {
        emitSessionTimeout(sessionTimeoutMessage);
        appendApiDebugRecord({
          level: 'error',
          method,
          path,
          message: 'Missing auth token',
          details: { session_timeout: true },
        });
        throw new Error(sessionTimeoutMessage);
      }
      headers.Authorization = `Bearer ${token}`;
    }

    const url = `${API_BASE}${path}`;
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
        appendApiDebugRecord({
          level: 'error',
          method,
          path,
          message: sessionTimeoutMessage,
          details: { session_timeout: true, reason: 'token_expired' },
        });
        throw new Error(sessionTimeoutMessage);
      }
      const mixedContentHint =
        typeof window !== 'undefined'
        && window.location.protocol === 'https:'
        && API_BASE.startsWith('http://')
          ? ' Mixed-content blocked: frontend is HTTPS but API URL is HTTP.'
          : '';
      const reason = error instanceof Error ? error.message : 'Failed to fetch';
      const message = `Network error: Unable to reach API at ${url}. ${reason}.${mixedContentHint}`;
      appendApiDebugRecord({
        level: 'error',
        method,
        path,
        message,
        details: {
          url,
          reason,
        },
      });
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
        appendApiDebugRecord({
          level: 'error',
          method,
          path,
          status: 401,
          message: sessionTimeoutMessage,
          details: { request: requestLabel, refresh_failed: true },
        });
        throw new Error(sessionTimeoutMessage);
      }
    }
  }

  if (!res.ok) {

    let message = `API Error (${res.status})`;
    const contentType = (res.headers.get('content-type') || '').toLowerCase();
    let errorPayload: unknown = null;
    let errorText: string | null = null;
    try {
      if (contentType.includes('application/json')) {
        const json = await res.json();
        errorPayload = json;
        message = extractApiErrorMessage(json, message);
      } else {
        const text = await res.text();
        errorText = text;
        if (text.trim()) {
          message = text.trim();
        }
      }
    } catch {
      // Ignore JSON parsing errors for non-JSON responses.
    }
    appendApiDebugRecord({
      level: 'error',
      method,
      path,
      status: res.status,
      message,
      details: {
        url: res.url,
        status: res.status,
        headers: toDebugHeaders(res),
        response: toDebugPayload(errorPayload ?? errorText),
      },
    });
    showAppErrorPopup(message, 'Request Failed');
    throw new Error(message);
  }

  if (responseType === 'blob') {
    const blob = await res.blob();
    appendApiDebugRecord({
      level: 'success',
      method,
      path,
      status: res.status,
      message: 'Binary response received',
      details: {
        url: res.url,
        status: res.status,
        headers: toDebugHeaders(res),
        response: {
          type: 'blob',
          mime_type: blob.type || res.headers.get('content-type') || null,
          size_bytes: blob.size,
        },
      },
    });
    return blob as T;
  }

  if (res.status === 204) {
    appendApiDebugRecord({
      level: 'success',
      method,
      path,
      status: res.status,
      message: 'No content response received',
      details: {
        url: res.url,
        status: res.status,
        headers: toDebugHeaders(res),
      },
    });
    return {} as T;
  }

  const json = (await res.json()) as T;
  appendApiDebugRecord({
    level: 'success',
    method,
    path,
    status: res.status,
    message: 'JSON response received',
    details: {
      url: res.url,
      status: res.status,
      headers: toDebugHeaders(res),
      response: toDebugPayload(json),
    },
  });
  return json;
}

export function getApiBaseUrl() {
  return API_BASE;
}
