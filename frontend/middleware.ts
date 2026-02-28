import { NextResponse, type NextRequest } from 'next/server';

const protectedPaths = ['/dashboard', '/invoices', '/clients', '/create', '/settings'];
const authPaths = ['/signin', '/signup'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get('token')?.value;

  const requiresAuth = protectedPaths.some((path) => pathname.startsWith(path));
  const isAuthPage = authPaths.some((path) => pathname.startsWith(path));

  if (requiresAuth && !token) {
    const url = new URL('/signin', request.url);
    url.searchParams.set('next', pathname);
    return NextResponse.redirect(url);
  }

  if (isAuthPage && token) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/invoices/:path*', '/clients/:path*', '/create/:path*', '/settings/:path*', '/signin', '/signup']
};