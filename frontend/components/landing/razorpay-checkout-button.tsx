'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
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

type ConfigResponse = { key_id: string | null };
type SubscriptionResponse = {
  subscription_id: string;
  status: string;
  short_url?: string | null;
};
type VerifyResponse = { verified: boolean };

export function RazorpayCheckoutButton({ className }: { className?: string }) {
  const [loading, setLoading] = useState(false);

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

      const config = await apiRequest<ConfigResponse>('/payments/config', { auth: false });
      const checkoutKey = config.key_id || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID;
      if (!checkoutKey) {
        throw new Error('Razorpay public key is missing.');
      }

      const subscription = await apiRequest<SubscriptionResponse>('/payments/subscriptions', {
        method: 'POST'
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
            window.location.href = '/dashboard';
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Unable to verify payment';
            alert(message);
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
      alert(message);
      setLoading(false);
    }
  };

  return (
    <Button onClick={launch} className={className}>
      {loading ? 'Launching Checkout...' : 'Start Secure Checkout'}
    </Button>
  );
}
