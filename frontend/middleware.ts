import { NextResponse, type NextRequest } from 'next/server';
import { canAccessAppPath, isAppProtectedPath, resolveEffectiveSubscriptionPlan } from '@/lib/subscription-access';

const authPaths = ['/signin', '/signup'];
const adminAuthPaths = ['/admin/signin'];
const adminProtectedPrefixes = ['/admin', '/newsletter'];
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

function resolveRoleFromToken(token: string | undefined): 'admin' | 'user' | null {
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  const role = payload && typeof payload.role === 'string' ? payload.role.toLowerCase() : '';
  if (role === 'admin' || role === 'user') {
    return role;
  }
  return null;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const normalizedPathname = pathname.toLowerCase();
  const token = request.cookies.get('token')?.value;

  if (pathname === '/' && token) {
    const role = resolveRoleFromToken(token);
    const targetPath = role === 'admin' ? '/admin' : '/dashboard';
    return withNoCache(NextResponse.redirect(new URL(targetPath, request.url)));
  }

  if (pathname === '/Newsletter' || pathname.startsWith('/Newsletter/')) {
    const url = request.nextUrl.clone();
    url.pathname = pathname.replace('/Newsletter', '/newsletter');
    return withNoCache(NextResponse.redirect(url));
  }

  const isAdminPath = adminProtectedPrefixes.some(
    (prefix) => normalizedPathname === prefix || normalizedPathname.startsWith(`${prefix}/`),
  );
  const isAdminAuthPage = adminAuthPaths.some(
    (path) => normalizedPathname === path || normalizedPathname.startsWith(`${path}/`),
  );

  if (isAdminPath && !isAdminAuthPage) {
    if (!token) {
      const url = new URL('/admin/signin', request.url);
      url.searchParams.set('next', pathname);
      return withNoCache(NextResponse.redirect(url));
    }

    const role = resolveRoleFromToken(token);
    if (role !== 'admin') {
      return withNoCache(NextResponse.redirect(new URL('/dashboard', request.url)));
    }

    return withNoCache(NextResponse.next());
  }

  if (isAdminAuthPage && token) {
    const role = resolveRoleFromToken(token);
    if (role === 'admin') {
      return withNoCache(NextResponse.redirect(new URL('/admin', request.url)));
    }
    return withNoCache(NextResponse.redirect(new URL('/dashboard', request.url)));
  }

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
    '/',
    '/admin/:path*',
    '/Admin/:path*',
    '/newsletter/:path*',
    '/Newsletter/:path*',
    '/dashboard/:path*',
    '/invoices/:path*',
    '/client-analytics/:path*',
    '/clients/:path*',
    '/create/:path*',
    '/hsn-sac-master-list/:path*',
    '/settings/:path*',
    '/upload/:path*',
    '/bills/:path*',
    '/signin',
    '/signup',
  ]
};
