import { NextResponse, type NextRequest } from 'next/server';
import { canAccessAppPath, isAppProtectedPath, resolveEffectiveSubscriptionPlan } from '@/lib/subscription-access';

const authPaths = ['/signin', '/signup'];
const noCacheValue = 'no-store, no-cache, must-revalidate';

function withNoCache(response: NextResponse) {
  response.headers.set('Cache-Control', noCacheValue);
  response.headers.set('Pragma', 'no-cache');
  response.headers.set('Expires', '0');
  return response;
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length < 2) return null;

  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=');
    const payload = atob(padded);
    return JSON.parse(payload) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function resolvePlanFromRequest(request: NextRequest, token: string | undefined) {
  const cookiePlan = request.cookies.get('subscription_plan')?.value;
  const cookieStatus = request.cookies.get('subscription_status')?.value;
  if (cookiePlan || cookieStatus) {
    return resolveEffectiveSubscriptionPlan(cookiePlan, cookieStatus);
  }

  if (!token) {
    return resolveEffectiveSubscriptionPlan('FREE', 'EXPIRED');
  }

  const payload = decodeJwtPayload(token);
  const tokenPlan =
    payload && typeof payload.subscription_plan === 'string' ? payload.subscription_plan : null;
  const tokenStatus =
    payload && typeof payload.subscription_status === 'string' ? payload.subscription_status : null;
  return resolveEffectiveSubscriptionPlan(tokenPlan, tokenStatus);
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get('token')?.value;

  const requiresAuth = isAppProtectedPath(pathname);
  const isAuthPage = authPaths.some((path) => pathname === path || pathname.startsWith(`${path}/`));

  if (requiresAuth && !token) {
    const url = new URL('/signin', request.url);
    url.searchParams.set('next', pathname);
    return withNoCache(NextResponse.redirect(url));
  }

  if (token) {
    const plan = resolvePlanFromRequest(request, token);

    if (requiresAuth && !canAccessAppPath(pathname, plan)) {
      return withNoCache(NextResponse.redirect(new URL('/dashboard', request.url)));
    }

    if (isAuthPage) {
      return withNoCache(NextResponse.redirect(new URL('/dashboard', request.url)));
    }
  }

  const response = NextResponse.next();
  if (requiresAuth || isAuthPage) {
    return withNoCache(response);
  }

  return response;
}

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/invoices/:path*',
    '/client-analytics/:path*',
    '/clients/:path*',
    '/create/:path*',
    '/settings/:path*',
    '/upload/:path*',
    '/bills/:path*',
    '/signin',
    '/signup',
  ]
};
