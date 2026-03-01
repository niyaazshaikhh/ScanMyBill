import { NextResponse, type NextRequest } from 'next/server';

const protectedPaths = ['/dashboard', '/invoices', '/clients', '/create', '/settings', '/upload', '/bills'];
const authPaths = ['/signin', '/signup'];
const noCacheValue = 'no-store, no-cache, must-revalidate';

function withNoCache(response: NextResponse) {
  response.headers.set('Cache-Control', noCacheValue);
  response.headers.set('Pragma', 'no-cache');
  response.headers.set('Expires', '0');
  return response;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get('token')?.value;

  const requiresAuth = protectedPaths.some((path) => pathname.startsWith(path));
  const isAuthPage = authPaths.some((path) => pathname.startsWith(path));

  if (requiresAuth && !token) {
    const url = new URL('/signin', request.url);
    url.searchParams.set('next', pathname);
    return withNoCache(NextResponse.redirect(url));
  }

  if (isAuthPage && token) {
    return withNoCache(NextResponse.redirect(new URL('/dashboard', request.url)));
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
    '/clients/:path*',
    '/create/:path*',
    '/settings/:path*',
    '/upload/:path*',
    '/bills/:path*',
    '/signin',
    '/signup',
  ]
};
