export type SubscriptionPlan = 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';
export type SubscriptionStatus = 'ACTIVE' | 'CANCELLED' | 'EXPIRED';

export const APP_PROTECTED_ROUTE_PREFIXES = [
  '/dashboard',
  '/invoices',
  '/client-analytics',
  '/clients',
  '/create',
  '/hsn-sac-master-list',
  '/settings',
  '/upload',
  '/bills',
] as const;

const allowedRoutePrefixesByPlan: Record<SubscriptionPlan, readonly string[]> = {
  FREE: ['/dashboard', '/settings'],
  STANDARD: ['/dashboard', '/invoices', '/settings'],
  PRO: ['/dashboard', '/invoices', '/client-analytics', '/settings'],
  BUSINESS: APP_PROTECTED_ROUTE_PREFIXES,
};

function matchesRoutePrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function normalizeSubscriptionPlan(plan?: string | null): SubscriptionPlan {
  const normalized = (plan || '').trim().toUpperCase();
  if (normalized === 'STANDARD' || normalized === 'PRO' || normalized === 'BUSINESS') {
    return normalized;
  }
  return 'FREE';
}

export function normalizeSubscriptionStatus(status?: string | null): SubscriptionStatus {
  const normalized = (status || '').trim().toUpperCase();
  if (normalized === 'ACTIVE' || normalized === 'CANCELLED') {
    return normalized;
  }
  return 'EXPIRED';
}

export function resolveEffectiveSubscriptionPlan(
  plan?: string | null,
  status?: string | null
): SubscriptionPlan {
  const normalizedPlan = normalizeSubscriptionPlan(plan);
  if (normalizedPlan === 'FREE') {
    return 'FREE';
  }
  return normalizeSubscriptionStatus(status) === 'ACTIVE' ? normalizedPlan : 'FREE';
}

export function isAppProtectedPath(pathname: string): boolean {
  return APP_PROTECTED_ROUTE_PREFIXES.some((prefix) => matchesRoutePrefix(pathname, prefix));
}

export function canAccessAppPath(pathname: string, plan: SubscriptionPlan): boolean {
  if (!isAppProtectedPath(pathname)) {
    return true;
  }
  return allowedRoutePrefixesByPlan[plan].some((prefix) => matchesRoutePrefix(pathname, prefix));
}

export function getAllowedAppRoutePrefixes(plan: SubscriptionPlan): readonly string[] {
  return allowedRoutePrefixesByPlan[plan];
}
