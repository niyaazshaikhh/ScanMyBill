"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";

export const dynamic = "force-dynamic";

import { RazorpayCheckoutButton } from "@/components/landing/razorpay-checkout-button";
import { SubscriptionBadge } from "@/components/SubscriptionBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";
import { updateAuthUser } from "@/lib/auth";

type SubscriptionPlan = "FREE" | "STANDARD" | "PRO" | "BUSINESS";
type SubscriptionStatus = "ACTIVE" | "CANCELLED" | "EXPIRED";

type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "user";
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
  const source = `${plan.item_name || ""} ${plan.id || ""}`.toLowerCase();
  if (source.includes("business")) return "BUSINESS";
  if (source.includes(" pro ")) return "PRO";
  if (source.includes("pro")) return "PRO";
  if (source.includes("standard")) return "STANDARD";
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

  const loadUser = useCallback(async () => {
    setLoadingUser(true);
    try {
      const profile = await apiRequest<CurrentUser>("/auth/me");
      setUser(profile);
      updateAuthUser({
        full_name: profile.full_name,
        email: profile.email,
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
  const canCancel = Boolean(user?.razorpay_subscription_id) && user?.subscription_status === "ACTIVE";

  const handleCheckoutSuccess = useCallback(async () => {
    setActionError(null);
    setActionMessage("Subscription updated successfully.");
    await loadUser();
  }, [loadUser]);

  const handleCancelSubscription = async () => {
    if (!canCancel) return;
    const confirmed = window.confirm(
      "Cancel your subscription now? This stops future charges on Razorpay.",
    );
    if (!confirmed) return;

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
    }
  };

  return (
    <div className="space-y-5">
      <h2 className="font-[var(--font-space)] text-2xl font-semibold">
        Settings
      </h2>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Account and Access</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
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

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Subscription</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 rounded-md border border-border bg-background/70 p-3 text-sm md:grid-cols-2">
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

          <div className="grid gap-3 lg:grid-cols-3">
            <div className="space-y-2 rounded-md border border-border bg-background/70 p-3 lg:col-span-2">
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

            <div className="grid gap-3">
              <div className="space-y-2 rounded-md border border-border bg-background/70 p-3">
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

              <div className="space-y-2 rounded-md border border-border bg-background/70 p-3">
                <p className="text-sm font-medium">Cancel</p>
                <Button
                  className="w-full"
                  variant="destructive"
                  onClick={handleCancelSubscription}
                  disabled={!canCancel || cancelLoading}
                >
                  {cancelLoading ? "Cancelling..." : "Cancel Subscription"}
                </Button>
              </div>
            </div>
          </div>

          {configError ? <p className="text-sm text-destructive">{configError}</p> : null}
          {actionError ? <p className="text-sm text-destructive">{actionError}</p> : null}
          {actionMessage ? <p className="text-sm text-emerald-700">{actionMessage}</p> : null}
        </CardContent>
      </Card>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Business Setup</CardTitle>
        </CardHeader>
        <CardContent>
          <Link
            href="/settings/personal_details"
            className="flex items-center justify-between rounded-md border border-border bg-background px-4 py-3 transition hover:bg-muted"
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
    </div>
  );
}
