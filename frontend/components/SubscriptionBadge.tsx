import { cn } from '@/lib/utils';

export type SubscriptionPlan = 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';

const planStyles: Record<SubscriptionPlan, string> = {
  FREE: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100',
  STANDARD: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-200',
  PRO: 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-200',
  BUSINESS: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-200'
};

const planLabels: Record<SubscriptionPlan, string> = {
  FREE: 'Free',
  STANDARD: 'Standard',
  PRO: 'Pro',
  BUSINESS: 'Business'
};

type SubscriptionBadgeProps = {
  plan?: string | null;
  className?: string;
};

function normalizePlan(plan?: string | null): SubscriptionPlan {
  const value = (plan || '').toUpperCase();
  if (value === 'STANDARD' || value === 'PRO' || value === 'BUSINESS') {
    return value;
  }
  return 'FREE';
}

export function SubscriptionBadge({ plan, className }: SubscriptionBadgeProps) {
  const normalizedPlan = normalizePlan(plan);

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-1 text-xs font-semibold',
        planStyles[normalizedPlan],
        className
      )}
    >
      {planLabels[normalizedPlan]}
    </span>
  );
}
