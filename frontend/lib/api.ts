import { getAuthToken } from '@/lib/auth';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  auth?: boolean;
  isFormData?: boolean;
  responseType?: 'json' | 'blob';
};

export async function apiRequest<T = unknown>(
  path: string,
  options: ApiOptions = {}
): Promise<T> {
  const {
    method = 'GET',
    body,
    auth = true,
    isFormData = false,
    responseType = 'json'
  } = options;

  const headers: HeadersInit = {};
  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  if (auth) {
    const token = getAuthToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body:
      body === undefined
        ? undefined
        : isFormData
        ? (body as FormData)
        : JSON.stringify(body)
  });

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