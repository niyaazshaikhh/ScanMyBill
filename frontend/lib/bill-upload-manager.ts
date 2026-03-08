import { API_BASE } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";
import { emitSessionTimeout } from "@/lib/session-timeout";

const SESSION_TIMEOUT_MESSAGE = "Session timed out. Please log in again.";

export type BillUploadStatus = "idle" | "uploading" | "success" | "error";

export type BillUploadState = {
  status: BillUploadStatus;
  progress: number;
  fileName: string | null;
  startedAt: number | null;
  finishedAt: number | null;
  response: unknown | null;
  error: string | null;
};

type BillUploadListener = (state: BillUploadState) => void;

type StartBillUploadOptions = {
  invoiceType?: "sales" | "purchase";
};

const INITIAL_UPLOAD_STATE: BillUploadState = {
  status: "idle",
  progress: 0,
  fileName: null,
  startedAt: null,
  finishedAt: null,
  response: null,
  error: null,
};

let currentState: BillUploadState = INITIAL_UPLOAD_STATE;
let activeRequestPromise: Promise<unknown> | null = null;
let activeXhr: XMLHttpRequest | null = null;
const listeners = new Set<BillUploadListener>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseJsonSafely(value: string): unknown | null {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function extractApiErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  const message = payload.message;
  if (typeof message === "string" && message.trim()) {
    return message.trim();
  }

  const error = payload.error;
  if (typeof error === "string" && error.trim()) {
    return error.trim();
  }

  return fallback;
}

function emitState() {
  for (const listener of listeners) {
    listener(currentState);
  }
}

function setUploadState(update: Partial<BillUploadState>) {
  currentState = {
    ...currentState,
    ...update,
  };
  emitState();
}

export function getBillUploadState(): BillUploadState {
  return currentState;
}

export function subscribeBillUpload(listener: BillUploadListener): () => void {
  listeners.add(listener);
  listener(currentState);
  return () => {
    listeners.delete(listener);
  };
}

export function startBillUpload(
  selectedFile: File,
  options: StartBillUploadOptions = {},
): Promise<unknown> {
  if (activeRequestPromise) {
    return Promise.reject(new Error("Another upload is already in progress."));
  }

  const token = getAuthToken();
  if (!token) {
    emitSessionTimeout(SESSION_TIMEOUT_MESSAGE);
    return Promise.reject(new Error(SESSION_TIMEOUT_MESSAGE));
  }

  const uploadPromise = new Promise<unknown>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    activeXhr = xhr;

    xhr.open("POST", `${API_BASE}/bills/upload`, true);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    setUploadState({
      status: "uploading",
      progress: 0,
      fileName: selectedFile.name,
      startedAt: Date.now(),
      finishedAt: null,
      response: null,
      error: null,
    });

    xhr.upload.onprogress = (event: ProgressEvent<EventTarget>) => {
      if (!event.lengthComputable || event.total <= 0) return;
      const nextProgress = Math.max(
        1,
        Math.min(99, Math.round((event.loaded / event.total) * 100)),
      );
      if (nextProgress !== currentState.progress) {
        setUploadState({ progress: nextProgress });
      }
    };

    xhr.onerror = () => {
      const message = "Network error while uploading the file.";
      setUploadState({
        status: "error",
        progress: 0,
        finishedAt: Date.now(),
        error: message,
      });
      reject(new Error(message));
    };

    xhr.onabort = () => {
      const message = "Upload cancelled.";
      setUploadState({
        status: "error",
        progress: 0,
        finishedAt: Date.now(),
        error: message,
      });
      reject(new Error(message));
    };

    xhr.onload = () => {
      const payload = parseJsonSafely(xhr.responseText || "");
      if (xhr.status >= 200 && xhr.status < 300) {
        setUploadState({
          status: "success",
          progress: 100,
          finishedAt: Date.now(),
          response: payload,
          error: null,
        });
        resolve(payload ?? {});
        return;
      }

      const message = extractApiErrorMessage(payload, `API Error (${xhr.status})`);
      if (xhr.status === 401) {
        emitSessionTimeout(SESSION_TIMEOUT_MESSAGE);
      }
      setUploadState({
        status: "error",
        progress: 0,
        finishedAt: Date.now(),
        response: payload,
        error: message,
      });
      reject(new Error(message));
    };

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("invoice_type", options.invoiceType || "sales");

    xhr.send(formData);
  });

  activeRequestPromise = uploadPromise.finally(() => {
    activeRequestPromise = null;
    activeXhr = null;
  });
  return activeRequestPromise;
}

export function isBillUploadInProgress(): boolean {
  return Boolean(activeXhr && currentState.status === "uploading");
}
