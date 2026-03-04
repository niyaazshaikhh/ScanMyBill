export const DEBUG_MODE_STORAGE_KEY = 'scanmybill_debug_mode_enabled';
export const DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY = 'scanmybill_dashboard_debug_upload_responses';
export const DEBUG_MODE_CHANGED_EVENT = 'scanmybill:debug-mode-changed';

export type DashboardDebugConsoleLevel = 'info' | 'success' | 'warning' | 'error';

export type DashboardDebugConsoleRecord = {
  id: string;
  created_at: string;
  level: DashboardDebugConsoleLevel;
  source: string;
  title: string;
  message: string;
  file_name?: string;
  details?: unknown;
};

export type DashboardDebugUploadRecord = {
  id: string;
  file_name: string;
  created_at: string;
  response: unknown;
};

type DashboardDebugConsoleInput = {
  level?: DashboardDebugConsoleLevel;
  source?: string;
  title: string;
  message: string;
  file_name?: string;
  details?: unknown;
};

const MAX_DEBUG_RECORDS = 100;

export function getDebugModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(DEBUG_MODE_STORAGE_KEY) === '1';
}

export function setDebugModeEnabled(value: boolean) {
  if (typeof window === 'undefined') return;
  if (value) {
    window.localStorage.setItem(DEBUG_MODE_STORAGE_KEY, '1');
  } else {
    window.localStorage.setItem(DEBUG_MODE_STORAGE_KEY, '0');
  }
  window.dispatchEvent(
    new CustomEvent<boolean>(DEBUG_MODE_CHANGED_EVENT, {
      detail: value,
    }),
  );
}

function toConsoleRecord(item: unknown): DashboardDebugConsoleRecord | null {
  if (typeof item !== 'object' || item === null) return null;

  const record = item as Partial<DashboardDebugConsoleRecord & DashboardDebugUploadRecord>;
  const id = typeof record.id === 'string' ? record.id : crypto.randomUUID();
  const createdAt = typeof record.created_at === 'string' ? record.created_at : new Date().toISOString();

  if (typeof record.title === 'string' && typeof record.message === 'string') {
    const level = record.level;
    return {
      id,
      created_at: createdAt,
      level: level === 'success' || level === 'warning' || level === 'error' ? level : 'info',
      source: typeof record.source === 'string' ? record.source : 'system',
      title: record.title,
      message: record.message,
      file_name: typeof record.file_name === 'string' ? record.file_name : undefined,
      details: record.details,
    };
  }

  // Backward compatibility for old upload-response records.
  if (typeof record.file_name === 'string' && 'response' in record) {
    return {
      id,
      created_at: createdAt,
      level: 'info',
      source: 'upload',
      title: 'Upload response captured',
      message: 'Legacy debug response record',
      file_name: record.file_name,
      details: record.response,
    };
  }

  return null;
}

export function readDashboardDebugResponses(): DashboardDebugConsoleRecord[] {
  if (typeof window === 'undefined') return [];
  const raw = window.localStorage.getItem(DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY);
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(toConsoleRecord)
      .filter((item): item is DashboardDebugConsoleRecord => item !== null);
  } catch {
    return [];
  }
}

export function writeDashboardDebugResponses(records: DashboardDebugConsoleRecord[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(
    DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY,
    JSON.stringify(records.slice(0, MAX_DEBUG_RECORDS)),
  );
}

export function clearDashboardDebugResponses() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY);
}

export function appendDashboardDebugRecord(input: DashboardDebugConsoleInput): DashboardDebugConsoleRecord[] {
  if (typeof window === 'undefined') return [];

  const nextEntry: DashboardDebugConsoleRecord = {
    id: crypto.randomUUID(),
    created_at: new Date().toISOString(),
    level: input.level || 'info',
    source: input.source || 'system',
    title: input.title,
    message: input.message,
    file_name: input.file_name,
    details: input.details,
  };

  const next = [nextEntry, ...readDashboardDebugResponses()].slice(0, MAX_DEBUG_RECORDS);
  writeDashboardDebugResponses(next);
  return next;
}
