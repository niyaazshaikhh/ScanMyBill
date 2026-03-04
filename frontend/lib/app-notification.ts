export type AppNotificationTone = "info" | "success" | "error";

export type AppNotificationPayload = {
  id?: string;
  title: string;
  message?: string;
  tone?: AppNotificationTone;
  durationMs?: number;
};

export const APP_NOTIFICATION_EVENT = "scanmybill:app-notification";

export function notifyApp(payload: AppNotificationPayload) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<AppNotificationPayload>(APP_NOTIFICATION_EVENT, {
      detail: payload,
    }),
  );
}

