'use client';

import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Crown, Leaf, Sparkles, type LucideIcon } from 'lucide-react';

import { RazorpayCheckoutButton } from '@/components/landing/razorpay-checkout-button';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiRequest } from '@/lib/api';
import { cn } from '@/lib/utils';

type SubscriptionPlan = 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';

type RazorpayPlanOption = {
  id: string;
  item_name?: string | null;
  mapped_plan?: SubscriptionPlan | null;
};

type PaymentConfigResponse = {
  key_id: string | null;
  plans: RazorpayPlanOption[];
};

const planCards: Array<{
  tier: Exclude<SubscriptionPlan, 'FREE'>;
  name: string;
  priceLabel: string;
  description: string;
  accentClass: string;
  icon: LucideIcon;
  points: string[];
}> = [
  {
    tier: 'STANDARD',
    name: 'Standard',
    priceLabel: 'Rs 1 / month',
    description: 'Good for one person who wants simple bill work.',
    accentClass: 'border-slate-200 bg-white/95',
    icon: Leaf,
    points: [
      'Use Dashboard, Invoices, and Settings',
      'Upload bills and keep records in one place',
    ],
  },
  {
    tier: 'PRO',
    name: 'Pro',
    priceLabel: 'Rs 101 / month',
    description: 'Best for small teams handling more clients.',
    accentClass: 'border-orange-300 bg-orange-50/40',
    icon: Sparkles,
    points: [
      'Everything in Standard plan',
      'Includes Client Analytics',
      'Better visibility on client performance',
      'Helpful for teams with daily bill work',
    ],
  },
  {
    tier: 'BUSINESS',
    name: 'Business',
    priceLabel: 'Rs 1001 / month',
    description: 'Best for busy businesses that need full access.',
    accentClass: 'border-teal-300 bg-teal-50/40',
    icon: Crown,
    points: [
      'Access to all main routes',
      'Best for full bill management',
      'Built for high daily bill volume',
      'Create and manage bills faster',
      'Suitable for teams needing full control',
      'Ideal for growing businesses',
    ],
  }
];

function inferPlanFromOption(plan: RazorpayPlanOption): Exclude<SubscriptionPlan, 'FREE'> | null {
  if (plan.mapped_plan && plan.mapped_plan !== 'FREE') {
    return plan.mapped_plan;
  }

  const source = `${plan.item_name || ''} ${plan.id || ''}`.toLowerCase();
  const normalized = source.replace(/[_-]+/g, ' ');

  if (
    normalized.includes('business')
    || normalized.includes('enterprise')
    || normalized.includes('premium')
  ) {
    return 'BUSINESS';
  }
  if (/\bpro\b/.test(normalized) || normalized.includes('professional')) {
    return 'PRO';
  }
  if (
    normalized.includes('standard')
    || normalized.includes('starter')
    || normalized.includes('basic')
  ) {
    return 'STANDARD';
  }

  return null;
}

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

  const planIdByTier = useMemo(() => {
    const map = new Map<Exclude<SubscriptionPlan, 'FREE'>, string>();
    for (const plan of plans) {
      const tier = inferPlanFromOption(plan);
      if (tier && !map.has(tier)) {
        map.set(tier, plan.id);
      }
    }
    return map;
  }, [plans]);

  return (
    <div className='space-y-4'>
      <div className='grid gap-4 md:grid-cols-3'>
        {planCards.map((plan) => {
          const planId = planIdByTier.get(plan.tier);
          const isConfigured = Boolean(planId);
          const PlanIcon = plan.icon;

          return (
            <Card key={plan.name} className={cn('flex h-full min-h-[320px] flex-col', plan.accentClass)}>
              <CardHeader className='space-y-3'>
                <div className='flex items-center gap-2'>
                  <span className='inline-flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-secondary-foreground'>
                    <PlanIcon className='h-4 w-4' />
                  </span>
                  <CardTitle className='font-[var(--font-space)] text-xl'>{plan.name}</CardTitle>
                </div>
                <CardDescription className='text-base font-semibold text-foreground'>{plan.priceLabel}</CardDescription>
              </CardHeader>
              <CardContent className='flex flex-1 flex-col gap-4'>
                <p className='text-sm text-muted-foreground'>{plan.description}</p>
                <ul className='space-y-1.5'>
                  {plan.points.map((point) => (
                    <li key={`${plan.name}-${point}`} className='flex items-start gap-2 text-xs text-muted-foreground'>
                      <CheckCircle2 className='mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600' />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
                <div className='mt-auto'>
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
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {configError ? <p className='text-xs text-destructive'>{configError}</p> : null}
      {!loadingPlans && !configError ? (
        <p className='text-xs text-muted-foreground'>
          Checkout buttons are enabled for plans mapped from Razorpay plan metadata.
        </p>
      ) : null}
    </div>
  );
}
