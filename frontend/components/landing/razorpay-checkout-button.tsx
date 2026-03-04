'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { PopupWindow } from '@/components/ui/popup-window';
import { apiRequest } from '@/lib/api';
import { getAuthToken } from '@/lib/auth';

async function loadRazorpayScript() {
  if (window.Razorpay) return true;

  return new Promise<boolean>((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

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
type SubscriptionResponse = {
  subscription_id: string;
  status: string;
  short_url?: string | null;
};
type VerifyResponse = { verified: boolean };

function formatPlanLabel(plan: RazorpayPlanOption) {
  const amount =
    typeof plan.amount === 'number' ? `Rs ${(plan.amount / 100).toLocaleString('en-IN')}` : 'Custom price';
  const cycle =
    plan.period && plan.interval ? ` / every ${plan.interval} ${plan.period}${plan.interval > 1 ? 's' : ''}` : '';
  return `${plan.item_name || 'Subscription Plan'} (${amount}${cycle})`;
}

type RazorpayCheckoutButtonProps = {
  className?: string;
  showPlanSelector?: boolean;
  defaultPlanId?: string;
  buttonLabel?: string;
  successRedirectPath?: string | null;
  onSuccess?: () => void | Promise<void>;
  disabled?: boolean;
};

export function RazorpayCheckoutButton({
  className,
  showPlanSelector = false,
  defaultPlanId,
  buttonLabel = 'Start Secure Checkout',
  successRedirectPath = '/dashboard',
  onSuccess,
  disabled = false,
}: RazorpayCheckoutButtonProps) {
  const [loading, setLoading] = useState(false);
  const [plans, setPlans] = useState<RazorpayPlanOption[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState(defaultPlanId || '');
  const [configError, setConfigError] = useState<string | null>(null);
  const [popupErrorMessage, setPopupErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!showPlanSelector) return;

    let active = true;
    const loadPlans = async () => {
      try {
        const config = await apiRequest<PaymentConfigResponse>('/payments/config', { auth: false });
        if (!active) return;
        setPlans(config.plans || []);

        const fallbackPlanId = config.plans?.[0]?.id || '';
        const nextPlanId =
          defaultPlanId && config.plans.some((plan) => plan.id === defaultPlanId) ? defaultPlanId : fallbackPlanId;
        setSelectedPlanId(nextPlanId);
      } catch (error) {
        if (!active) return;
        setConfigError(error instanceof Error ? error.message : 'Unable to load plan options');
      }
    };

    void loadPlans();
    return () => {
      active = false;
    };
  }, [showPlanSelector, defaultPlanId]);

  const launch = async () => {
    if (loading) return;
    setLoading(true);

    try {
      const token = getAuthToken();
      if (!token) {
        window.location.href = '/signin?next=/pricing';
        return;
      }

      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded) {
        throw new Error('Failed to load Razorpay checkout script.');
      }

      const config = await apiRequest<PaymentConfigResponse>('/payments/config', { auth: false });
      const checkoutKey = config.key_id || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID;
      if (!checkoutKey) {
        throw new Error('Razorpay public key is missing.');
      }

      const planId = defaultPlanId || selectedPlanId || config.plans?.[0]?.id;
      if (!planId) {
        throw new Error('No Razorpay plan is configured.');
      }

      const subscription = await apiRequest<SubscriptionResponse>('/payments/subscriptions', {
        method: 'POST',
        body: { plan_id: planId }
      });

      if (!window.Razorpay) {
        throw new Error('Razorpay checkout is not available.');
      }

      const razorpay = new window.Razorpay({
        key: checkoutKey,
        subscription_id: subscription.subscription_id,
        name: 'ScanMyBill.in',
        description: 'ScanMyBill Pro Subscription',
        theme: { color: '#d85b1b' },
        handler: async (response) => {
          try {
            const verification = await apiRequest<VerifyResponse>('/payments/verify', {
              method: 'POST',
              body: {
                razorpay_signature: response.razorpay_signature,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_subscription_id: response.razorpay_subscription_id
              }
            });
            if (!verification.verified) {
              throw new Error('Payment verification failed.');
            }
            if (onSuccess) {
              await onSuccess();
            }
            if (successRedirectPath) {
              window.location.href = successRedirectPath;
              return;
            }
            setLoading(false);
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Unable to verify payment';
            setPopupErrorMessage(message);
            setLoading(false);
          }
        },
        modal: {
          ondismiss: () => setLoading(false)
        }
      });

      razorpay.open();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to start payment';
      setPopupErrorMessage(message);
      setLoading(false);
    }
  };

  return (
    <div className='space-y-2'>
      {showPlanSelector ? (
        <>
          <label className='block text-sm font-medium text-foreground' htmlFor='plan-select'>
            Choose plan
          </label>
          <select
            id='plan-select'
            value={selectedPlanId}
            onChange={(event) => setSelectedPlanId(event.target.value)}
            className='h-10 w-full rounded-md border border-border bg-background px-3 text-sm'
          >
            {plans.length === 0 ? <option value=''>No plans found</option> : null}
            {plans.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {formatPlanLabel(plan)}
              </option>
            ))}
          </select>
          {configError ? <p className='text-xs text-destructive'>{configError}</p> : null}
        </>
      ) : null}

      <Button
        onClick={launch}
        className={className}
        disabled={disabled || loading || (showPlanSelector && !selectedPlanId)}
      >
        {loading ? 'Launching Checkout...' : buttonLabel}
      </Button>
      <PopupWindow
        open={Boolean(popupErrorMessage)}
        title='Checkout Error'
        message={popupErrorMessage || ''}
        confirmLabel='Close'
        onConfirm={() => setPopupErrorMessage(null)}
      />
    </div>
  );
}
