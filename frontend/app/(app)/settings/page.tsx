"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, BellOff, ChevronDown, ChevronRight, Eye, EyeOff, X } from "lucide-react";

export const dynamic = "force-dynamic";

import { RazorpayCheckoutButton } from "@/components/landing/razorpay-checkout-button";
import { SubscriptionBadge } from "@/components/SubscriptionBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PopupWindow } from "@/components/ui/popup-window";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";
import { openAboutModal } from "@/lib/about-modal";
import { updateAuthUser } from "@/lib/auth";
import { setDebugModeEnabled } from "@/lib/debugging";

type SubscriptionPlan = "FREE" | "STANDARD" | "PRO" | "BUSINESS";
type SubscriptionStatus = "ACTIVE" | "CANCELLED" | "EXPIRED";

type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "user";
  notifications_enabled: boolean;
  subscription_plan: SubscriptionPlan;
  subscription_status: SubscriptionStatus;
  razorpay_subscription_id?: string | null;
  subscription_started_at?: string | null;
  subscription_expires_at?: string | null;
  created_at: string;
};

type RazorpayPlanOption = {
  id: string;
  item_name?: string | null;
  interval?: number | null;
  period?: string | null;
  amount?: number | null;
  currency?: string | null;
  mapped_plan?: SubscriptionPlan | null;
};

type PaymentConfigResponse = {
  key_id: string | null;
  plans: RazorpayPlanOption[];
};

type CancelSubscriptionResponse = {
  cancelled: boolean;
  subscription_id?: string | null;
  status: SubscriptionStatus;
  expires_at?: string | null;
};

const planRank: Record<SubscriptionPlan, number> = {
  FREE: 0,
  STANDARD: 1,
  PRO: 2,
  BUSINESS: 3,
};

function inferPlanFromOption(plan: RazorpayPlanOption): SubscriptionPlan | null {
  if (plan.mapped_plan) {
    return plan.mapped_plan;
  }

  const source = `${plan.item_name || ""} ${plan.id || ""}`.toLowerCase();
  const normalized = source.replace(/[_-]+/g, " ");

  if (
    normalized.includes("business")
    || normalized.includes("enterprise")
    || normalized.includes("premium")
  ) {
    return "BUSINESS";
  }
  if (/\bpro\b/.test(normalized) || normalized.includes("professional")) {
    return "PRO";
  }
  if (
    normalized.includes("standard")
    || normalized.includes("starter")
    || normalized.includes("basic")
  ) {
    return "STANDARD";
  }
  return null;
}

function findPlanIdForPlan(plans: RazorpayPlanOption[], currentPlan: SubscriptionPlan): string | null {
  const matched = plans.find((plan) => inferPlanFromOption(plan) === currentPlan);
  return matched?.id || null;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleString("en-IN", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusBadgeVariant(status?: SubscriptionStatus) {
  if (status === "ACTIVE") return "success";
  if (status === "CANCELLED") return "secondary";
  return "outline";
}

export default function SettingsPage() {
  useAuthGuard();

  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);
  const [planConfig, setPlanConfig] = useState<PaymentConfigResponse | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [notificationUpdating, setNotificationUpdating] = useState(false);
  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [subscriptionExpanded, setSubscriptionExpanded] = useState(false);
  const [debugModeEnabled, setDebugModeEnabledState] = useState(false);

  const loadUser = useCallback(async () => {
    setLoadingUser(true);
    try {
      const profile = await apiRequest<CurrentUser>("/auth/me");
      setUser(profile);
      updateAuthUser({
        full_name: profile.full_name,
        email: profile.email,
        notifications_enabled: profile.notifications_enabled,
        subscription_plan: profile.subscription_plan,
        subscription_status: profile.subscription_status,
        razorpay_subscription_id: profile.razorpay_subscription_id,
        subscription_started_at: profile.subscription_started_at,
        subscription_expires_at: profile.subscription_expires_at,
      });
    } catch {
      setUser(null);
    } finally {
      setLoadingUser(false);
    }
  }, []);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  useEffect(() => {
    let active = true;
    apiRequest<PaymentConfigResponse>("/payments/config", { auth: false })
      .then((response) => {
        if (!active) return;
        setPlanConfig(response);
      })
      .catch((error) => {
        if (!active) return;
        setConfigError(error instanceof Error ? error.message : "Unable to load subscription plans");
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setDebugModeEnabledState(false);
    setDebugModeEnabled(false);
  }, []);

  useEffect(() => {
    if (!helpOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHelpOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [helpOpen]);

  const currentPlan: SubscriptionPlan = user?.subscription_plan || "FREE";
  const currentPlanId = useMemo(
    () => findPlanIdForPlan(planConfig?.plans || [], currentPlan),
    [planConfig?.plans, currentPlan],
  );

  const hasHigherPlan = useMemo(
    () =>
      (planConfig?.plans || []).some((plan) => {
        const mapped = inferPlanFromOption(plan);
        if (!mapped) return false;
        return planRank[mapped] > planRank[currentPlan];
      }),
    [currentPlan, planConfig?.plans],
  );

  const canRenew = currentPlan !== "FREE" && Boolean(currentPlanId);
  const canCancel = user?.subscription_status === "ACTIVE" && user?.subscription_plan !== "FREE";

  const handleCheckoutSuccess = useCallback(async () => {
    setActionError(null);
    setActionMessage("Subscription updated successfully.");
    await loadUser();
  }, [loadUser]);

  const handleCancelSubscription = async () => {
    if (!canCancel) return;

    setCancelLoading(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const response = await apiRequest<CancelSubscriptionResponse>("/payments/subscriptions/cancel", {
        method: "POST",
      });
      if (!response.cancelled) {
        throw new Error("Unable to cancel subscription.");
      }
      setActionMessage("Subscription cancelled successfully.");
      await loadUser();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to cancel subscription");
    } finally {
      setCancelLoading(false);
      setCancelConfirmOpen(false);
    }
  };

  const handleToggleDebugMode = () => {
    const next = !debugModeEnabled;
    setDebugModeEnabledState(next);
    setDebugModeEnabled(next);
  };

  const handleToggleNotifications = async () => {
    if (!user || notificationUpdating) return;

    const next = !user.notifications_enabled;
    setNotificationUpdating(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await apiRequest<CurrentUser>("/users/notification-preference", {
        method: "PUT",
        body: { notifications_enabled: next },
      });
      setUser(updated);
      updateAuthUser({ notifications_enabled: updated.notifications_enabled });
      setActionMessage(
        updated.notifications_enabled
          ? "Notifications turned on."
          : "Notifications turned off.",
      );
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Failed to update notification preference");
    } finally {
      setNotificationUpdating(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="font-[var(--font-space)] text-2xl font-semibold">
        Settings
      </h2>

      <Card className="bg-card/85">
        <CardHeader className="space-y-1 p-4 pb-2">
          <CardTitle className="text-base">Account and Access</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 p-4 pt-0 text-sm">
          <p>
            <span className="font-medium">Name:</span> {loadingUser ? "Loading..." : user?.full_name || "-"}
          </p>
          <p>
            <span className="font-medium">Email:</span> {loadingUser ? "Loading..." : user?.email || "-"}
          </p>
          <p>
            <span className="font-medium">Role:</span>{" "}
            <Badge variant="secondary">{loadingUser ? "..." : user?.role || "user"}</Badge>
          </p>
          <p>
            <span className="font-medium">Joined:</span> {formatDate(user?.created_at)}
          </p>
        </CardContent>
      </Card>

      <Card className="bg-card/85">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 p-4 pb-2">
          <CardTitle className="text-base">Subscription</CardTitle>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSubscriptionExpanded((prev) => !prev)}
            className="h-8 gap-1 px-2"
            aria-expanded={subscriptionExpanded}
            aria-label={subscriptionExpanded ? "Collapse subscription card" : "Expand subscription card"}
          >
            {subscriptionExpanded ? "Collapse" : "Expand"}
            <ChevronDown className={`h-4 w-4 transition-transform ${subscriptionExpanded ? "rotate-180" : ""}`} />
          </Button>
        </CardHeader>
        {subscriptionExpanded ? (
          <CardContent className="space-y-3 p-4 pt-0">
          <div className="grid gap-2 rounded-md border border-border bg-background/70 p-2.5 text-sm md:grid-cols-2">
            <p className="flex items-center gap-2">
              <span className="font-medium">Current Plan:</span>
              <SubscriptionBadge plan={currentPlan} />
            </p>
            <p className="flex items-center gap-2">
              <span className="font-medium">Status:</span>
              <Badge variant={statusBadgeVariant(user?.subscription_status)}>
                {user?.subscription_status || "-"}
              </Badge>
            </p>
            <p>
              <span className="font-medium">Started On:</span>{" "}
              {formatDate(user?.subscription_started_at)}
            </p>
            <p>
              <span className="font-medium">Expires On:</span>{" "}
              {formatDate(user?.subscription_expires_at)}
            </p>
          </div>

          <div className="grid gap-2.5 lg:grid-cols-3">
            <div className="space-y-1.5 rounded-md border border-border bg-background/70 p-2.5 lg:col-span-2">
              <p className="text-sm font-medium">Upgrade</p>
              <p className="text-xs text-muted-foreground">
                Move to a higher plan with immediate checkout.
              </p>
              <RazorpayCheckoutButton
                className="w-full"
                showPlanSelector
                buttonLabel="Upgrade Plan"
                successRedirectPath={null}
                onSuccess={handleCheckoutSuccess}
                disabled={!hasHigherPlan}
              />
              {!hasHigherPlan ? (
                <p className="text-xs text-muted-foreground">
                  No higher plan is configured at the moment.
                </p>
              ) : null}
            </div>

            <div className="grid gap-2.5">
              <div className="space-y-1.5 rounded-md border border-border bg-background/70 p-2.5">
                <p className="text-sm font-medium">Renew</p>
                <RazorpayCheckoutButton
                  className="w-full"
                  buttonLabel="Renew Current Plan"
                  defaultPlanId={currentPlanId || undefined}
                  successRedirectPath={null}
                  onSuccess={handleCheckoutSuccess}
                  disabled={!canRenew}
                />
              </div>

              <div className="space-y-1.5 rounded-md border border-border bg-background/70 p-2.5">
                <p className="text-sm font-medium">Cancel</p>
                <Button
                  className="w-full"
                  variant="destructive"
                  onClick={() => setCancelConfirmOpen(true)}
                  disabled={!canCancel || cancelLoading}
                >
                  {cancelLoading ? "Cancelling..." : "Cancel Subscription"}
                </Button>
              </div>
            </div>
          </div>

          {configError ? <p className="text-sm text-destructive">{configError}</p> : null}
          {actionError ? <p className="text-sm text-destructive">{actionError}</p> : null}
          {actionMessage ? <p className="text-sm text-emerald-700 dark:text-emerald-300">{actionMessage}</p> : null}
          </CardContent>
        ) : null}
      </Card>

      <Card className="bg-card/85">
        <CardHeader className="space-y-1 p-4 pb-2">
          <CardTitle className="text-base">Business Setup</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <Link
            href="/settings/personal_details"
            className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2.5 transition hover:bg-muted"
          >
            <div>
              <p className="text-sm font-medium">Personal Details</p>
              <p className="text-xs text-muted-foreground">
                Add Company Name and GST/IN to improve bill type identification.
              </p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </Link>
        </CardContent>
      </Card>

      <Card className="bg-card/85">
        <CardHeader className="space-y-1 p-4 pb-2">
          <CardTitle className="text-base">Developer Tools</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-2.5 p-4 pt-0">
          <p className="text-sm text-muted-foreground">
            Toggle Debug Console visibility on the dashboard upload flow.
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={handleToggleDebugMode}
            className="shrink-0"
          >
            {debugModeEnabled ? (
              <Eye className="h-4 w-4" />
            ) : (
              <EyeOff className="h-4 w-4" />
            )}
            Debugging mode {debugModeEnabled ? "On" : "Off"}
          </Button>
        </CardContent>
      </Card>

      <Card className="bg-card/85">
        <CardHeader className="space-y-1 p-4 pb-2">
          <CardTitle className="text-base">Notification Preferences</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-2.5 p-4 pt-0">
          <p className="text-sm text-muted-foreground">
            Turn pop-up notifications on or off for this account.
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => void handleToggleNotifications()}
            disabled={notificationUpdating || loadingUser || !user}
            className="shrink-0"
          >
            {user?.notifications_enabled ? (
              <Bell className="h-4 w-4" />
            ) : (
              <BellOff className="h-4 w-4" />
            )}
            Notifications {user?.notifications_enabled ? "On" : "Off"}
          </Button>
        </CardContent>
      </Card>

      <Card className="bg-card/85">
        <CardHeader className="space-y-1 p-4 pb-2">
          <CardTitle className="text-base">Contact & Help</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2.5 p-4 pt-0 text-sm">
          <p className="text-muted-foreground">
            Need help with billing, subscriptions, or account setup?
          </p>
          <p>
            <span className="font-medium">Support Email:</span>{" "}
            <a
              className="text-primary hover:underline"
              href="mailto:scanmybill@gmail.com?subject=ScanMyBill%20Support%20Request"
            >
              scanmybill@gmail.com
            </a>
          </p>
          <button
            type="button"
            onClick={() => setHelpOpen(true)}
            className="inline-flex w-full items-center justify-between rounded-md border border-border bg-background px-3 py-2.5 text-left transition hover:bg-muted"
          >
            <span className="text-sm font-medium">Help, FAQ and About</span>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </button>
        </CardContent>
      </Card>

      {helpOpen ? (
        <div
          className="fixed inset-0 z-50 bg-black/40 px-4 py-6"
          onClick={() => setHelpOpen(false)}
          role="presentation"
        >
          <div
            className="mx-auto w-full max-w-md rounded-lg border border-border bg-background shadow-xl"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Help and About"
          >
            <div className="flex items-start justify-between border-b border-border px-4 py-3">
              <p className="font-semibold">Help, FAQ and About</p>
              <button
                type="button"
                onClick={() => setHelpOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Close help popup"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 px-4 py-3 text-sm">
              <p className="text-muted-foreground">
                ScanMyBill helps you create, export, and manage GST invoices and delivery challans in one place.
              </p>
              <p>
                <span className="font-medium">Support:</span>{" "}
                <a className="text-primary hover:underline" href="mailto:scanmybill@gmail.com">
                  scanmybill@gmail.com
                </a>
              </p>
              <p className="text-muted-foreground">Quick FAQ:</p>
              <p className="text-xs text-muted-foreground">1. Use Create pages to export PDFs or save records to database.</p>
              <p className="text-xs text-muted-foreground">2. Manage reusable masters from HSN/SAC and Clients modules.</p>
              <p className="text-xs text-muted-foreground">3. Use Settings for plan management and personal details updates.</p>
              <div className="pt-1">
                <button
                  type="button"
                  className="text-primary hover:underline"
                  onClick={() => {
                    setHelpOpen(false);
                    openAboutModal();
                  }}
                >
                  Open About popup
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      <PopupWindow
        open={cancelConfirmOpen}
        title="Cancel Subscription"
        message="Cancel your subscription now? This stops future charges on Razorpay."
        confirmLabel={cancelLoading ? "Cancelling..." : "Cancel Subscription"}
        cancelLabel="Keep Subscription"
        confirmVariant="destructive"
        loading={cancelLoading}
        onCancel={() => {
          if (cancelLoading) return;
          setCancelConfirmOpen(false);
        }}
        onConfirm={() => {
          if (cancelLoading) return;
          void handleCancelSubscription();
        }}
      />
    </div>
  );
}


