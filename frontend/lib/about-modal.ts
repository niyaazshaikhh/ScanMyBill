export const OPEN_ABOUT_MODAL_EVENT = 'scanmybill:open-about-modal';
export const PENDING_ABOUT_MODAL_KEY = 'scanmybill:pending-about-modal';

export function openAboutModal() {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(PENDING_ABOUT_MODAL_KEY, '1');
  window.dispatchEvent(new CustomEvent(OPEN_ABOUT_MODAL_EVENT));
}

export function consumePendingAboutModal(): boolean {
  if (typeof window === 'undefined') return false;
  if (sessionStorage.getItem(PENDING_ABOUT_MODAL_KEY) !== '1') return false;
  sessionStorage.removeItem(PENDING_ABOUT_MODAL_KEY);
  return true;
}
