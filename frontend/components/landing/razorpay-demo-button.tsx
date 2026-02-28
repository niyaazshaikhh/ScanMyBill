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
  mock: boolean;
};

export function RazorpayDemoButton() {
  const [loading, setLoading] = useState(false);

  const launch = async () => {
    if (loading) return;
    setLoading(true);

    try {
      const token = getAuthToken();
      if (!token) {
        window.location.href = '/signin?next=/';
        return;
      }

      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded) {
        alert('Failed to load Razorpay checkout script.');
        return;
      }

      const config = await apiRequest<ConfigResponse>('/payments/config', { auth: false });
      const subscription = await apiRequest<SubscriptionResponse>('/payments/subscriptions/demo', {
        method: 'POST'
      });

      if (subscription.mock || !window.Razorpay) {
        alert(`Demo subscription created: ${subscription.subscription_id}`);
        return;
      }

      const razorpay = new window.Razorpay({
        key: config.key_id || process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID,
        subscription_id: subscription.subscription_id,
        name: 'ScanMyBill.in',
        description: 'SaaS Subscription Demo',
        theme: { color: '#d85b1b' }
      });
      razorpay.open();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to start payment';
      alert(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button onClick={launch} variant='secondary' className='w-full sm:w-auto'>
      {loading ? 'Starting Checkout...' : 'Try Razorpay Subscription Demo'}
    </Button>
  );
}
