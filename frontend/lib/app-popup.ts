export type AppPopupTone = 'info' | 'success' | 'error';

export type AppPopupPayload = {
  title: string;
  message: string;
  tone?: AppPopupTone;
  confirmLabel?: string;
};

export const APP_POPUP_EVENT = 'scanmybill:app-popup';

export function openAppPopup(payload: AppPopupPayload) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<AppPopupPayload>(APP_POPUP_EVENT, {
      detail: payload,
    }),
  );
}

export function showAppErrorPopup(message: string, title = 'Error') {
  openAppPopup({
    title,
    message,
    tone: 'error',
    confirmLabel: 'OK',
  });
}

export function showAppSuccessPopup(message: string, title = 'Success') {
  openAppPopup({
    title,
    message,
    tone: 'success',
    confirmLabel: 'OK',
  });
}

export function showAppInfoPopup(message: string, title = 'Message') {
  openAppPopup({
    title,
    message,
    tone: 'info',
    confirmLabel: 'OK',
  });
}
