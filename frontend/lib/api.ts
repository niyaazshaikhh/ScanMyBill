import type { AuthUser } from '@/lib/auth';
import { getAuthToken, getAuthUser, isAuthTokenExpired, setAuthSession } from '@/lib/auth';
import { emitSessionTimeout } from '@/lib/session-timeout';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

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

  const executeRequest = async (tokenOverride?: string | null) => {
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
        throw new Error(sessionTimeoutMessage);
      }
      const mixedContentHint =
        typeof window !== 'undefined'
        && window.location.protocol === 'https:'
        && API_BASE.startsWith('http://')
          ? ' Mixed-content blocked: frontend is HTTPS but API URL is HTTP.'
          : '';
      const reason = error instanceof Error ? error.message : 'Failed to fetch';
      throw new Error(
        `Network error: Unable to reach API at ${url}. ${reason}.${mixedContentHint}`,
      );
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
    try {
      const json = await res.json();
      message = json.detail || message;
    } catch {
      // Ignore JSON parsing errors for non-JSON responses.
    }
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
  return API_BASE;
}
