'use client';

import { useEffect, useMemo, useState } from 'react';

import { RazorpayCheckoutButton } from '@/components/landing/razorpay-checkout-button';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils';

type RazorpayPlanOption = {
  id: string;
  amount?: number | null;
};

type PaymentConfigResponse = {
  key_id: string | null;
  plans: RazorpayPlanOption[];
};

const planCards = [
  {
    name: 'Standard',
    priceLabel: 'Rs 1 / month',
    amountPaise: 100,
    description: 'Best for trying ScanMyBill with core invoice and GST workflow features.',
    accentClass: 'border-slate-200'
  },
  {
    name: 'Pro',
    priceLabel: 'Rs 101 / month',
    amountPaise: 10100,
    description: 'Great for growing teams that need regular OCR processing and analytics.',
    accentClass: 'border-orange-300 bg-orange-50/40'
  },
  {
    name: 'Business',
    priceLabel: 'Rs 1001 / month',
    amountPaise: 100100,
    description: 'Built for high-volume operations with advanced billing and reporting needs.',
    accentClass: 'border-teal-300 bg-teal-50/40'
  }
] as const;

export function PricingPlanCards() {
  const [plans, setPlans] = useState<RazorpayPlanOption[]>([]);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const loadPlans = async () => {
      setLoadingPlans(true);
      setConfigError(null);

      try {
        const config = await apiRequest<PaymentConfigResponse>('/payments/config', { auth: false });
        if (!active) return;
        setPlans(config.plans || []);
      } catch (error) {
        if (!active) return;
        setConfigError(error instanceof Error ? error.message : 'Unable to load plan configuration');
      } finally {
        if (active) {
          setLoadingPlans(false);
        }
      }
    };

    void loadPlans();
    return () => {
      active = false;
    };
  }, []);

  const planIdByAmount = useMemo(() => {
    const map = new Map<number, string>();
    for (const plan of plans) {
      if (typeof plan.amount === 'number') {
        map.set(plan.amount, plan.id);
      }
    }
    return map;
  }, [plans]);

  return (
    <div className='space-y-4'>
      <div className='grid gap-4 md:grid-cols-3'>
        {planCards.map((plan) => {
          const planId = planIdByAmount.get(plan.amountPaise);
          const isConfigured = Boolean(planId);

          return (
            <Card key={plan.name} className={cn('flex h-full flex-col', plan.accentClass)}>
              <CardHeader>
                <CardTitle className='font-[var(--font-space)] text-xl'>{plan.name}</CardTitle>
                <CardDescription className='text-base font-semibold text-foreground'>{plan.priceLabel}</CardDescription>
              </CardHeader>
              <CardContent className='flex flex-1 flex-col justify-between gap-4'>
                <p className='text-sm text-muted-foreground'>{plan.description}</p>
                {loadingPlans ? (
                  <Button className='w-full' disabled>
                    Loading plan...
                  </Button>
                ) : isConfigured ? (
                  <RazorpayCheckoutButton className='w-full' defaultPlanId={planId} />
                ) : (
                  <Button className='w-full' disabled>
                    Plan not configured
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {configError ? <p className='text-xs text-destructive'>{configError}</p> : null}
      {!loadingPlans && !configError ? (
        <p className='text-xs text-muted-foreground'>
          Checkout buttons are enabled only for plans that match configured Razorpay plan amounts.
        </p>
      ) : null}
    </div>
  );
}
