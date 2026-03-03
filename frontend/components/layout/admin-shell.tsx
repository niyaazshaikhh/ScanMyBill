'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { BarChart3, Bell, FileText, LayoutDashboard, Lock, Menu, PlusCircle, Settings, UserCircle2, Users, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { SubscriptionBadge } from '@/components/SubscriptionBadge';
import { Button } from '@/components/ui/button';
import { apiRequest } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { clearAuthSession, getAuthToken, getAuthUser, updateAuthUser } from '@/lib/auth';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import {
  canAccessAppPath,
  resolveEffectiveSubscriptionPlan,
  type SubscriptionPlan,
  type SubscriptionStatus,
} from '@/lib/subscription-access';
import { cn } from '@/lib/utils';

const nav = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/invoices', label: 'Invoices', icon: FileText },
  { href: '/client-analytics', label: 'Client Analytics', icon: BarChart3 },
  { href: '/clients', label: 'Clients', icon: Users },
  { href: '/create', label: 'Create', icon: PlusCircle },
  { href: '/settings', label: 'Settings', icon: Settings }
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [displayName, setDisplayName] = useState('User');
  const [subscriptionPlan, setSubscriptionPlan] = useState<SubscriptionPlan>('FREE');
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionStatus>('EXPIRED');

  useAuthGuard();

  useEffect(() => {
    let active = true;

    const syncUser = async () => {
      const user = getAuthUser();
      setDisplayName(user?.full_name || user?.email || 'User');
      setSubscriptionPlan(user?.subscription_plan || 'FREE');
      setSubscriptionStatus(user?.subscription_status || 'EXPIRED');

      if (!getAuthToken()) {
        setSubscriptionPlan('FREE');
        setSubscriptionStatus('EXPIRED');
        return;
      }

      try {
        const profile = await apiRequest<{
          id: string;
          full_name: string;
          email: string;
          subscription_plan: SubscriptionPlan;
          subscription_status: 'ACTIVE' | 'CANCELLED' | 'EXPIRED';
        }>('/users/me');
        if (!active) return;

        setDisplayName(profile.full_name || profile.email || 'User');
        setSubscriptionPlan(profile.subscription_plan || 'FREE');
        setSubscriptionStatus(profile.subscription_status || 'EXPIRED');
        updateAuthUser({
          full_name: profile.full_name,
          email: profile.email,
          subscription_plan: profile.subscription_plan,
          subscription_status: profile.subscription_status,
        });
      } catch {
        if (!active) return;
      }
    };

    void syncUser();
    const onStorage = () => {
      void syncUser();
    };

    window.addEventListener('storage', onStorage);
    return () => {
      active = false;
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  const effectivePlan = useMemo(
    () => resolveEffectiveSubscriptionPlan(subscriptionPlan, subscriptionStatus),
    [subscriptionPlan, subscriptionStatus]
  );

  const title = useMemo(() => {
    return nav.find((item) => pathname.startsWith(item.href))?.label || 'Dashboard';
  }, [pathname]);

  const logout = async () => {
    setLoggingOut(true);
    try {
      await apiRequest('/auth/logout', { method: 'POST' });
    } catch {
      // Always clear local auth state even if revoke call fails.
    } finally {
      clearAuthSession();
      if (typeof window !== 'undefined') {
        localStorage.removeItem('scanmybill_token');
        window.history.pushState(null, '', '/signin');
      }
      router.replace('/signin');
      router.refresh();
      if (typeof window !== 'undefined') {
        window.location.replace('/signin');
      }
      setLoggingOut(false);
    }
  };

  return (
    <div className='flex min-h-screen'>
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 min-h-0 flex-col border-r border-border bg-white/95 p-4 transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
          collapsed && 'lg:w-20'
        )}
      >
        <div className='mb-6 flex items-center justify-between'>
          <Link
            href='/dashboard'
            className={cn(
              'font-[var(--font-space)] text-primary',
              collapsed
                ? 'grid h-10 w-10 place-items-center rounded-md border border-primary/20 bg-primary/10 text-sm font-bold tracking-wide lg:mx-auto'
                : 'text-xl font-semibold'
            )}
            aria-label={collapsed ? 'SMB' : 'ScanMyBill.in'}
          >
            {collapsed ? 'SMB' : 'ScanMyBill.in'}
          </Link>
          <Button variant='ghost' size='icon' className='lg:hidden' onClick={() => setOpen(false)}>
            <X className='h-5 w-5' />
          </Button>
        </div>

        <nav className='flex-1 space-y-1'>
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            const isLocked = !canAccessAppPath(item.href, effectivePlan);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition hover:bg-muted',
                  active && 'bg-secondary text-secondary-foreground',
                  isLocked && 'cursor-not-allowed opacity-60 hover:bg-transparent',
                  collapsed && 'lg:justify-center'
                )}
                aria-disabled={isLocked}
                onClick={(event) => {
                  if (isLocked) {
                    event.preventDefault();
                    return;
                  }
                  setOpen(false);
                }}
              >
                <Icon className='h-4 w-4 shrink-0' />
                <span className={cn(collapsed && 'lg:hidden')}>{item.label}</span>
                {isLocked ? <Lock className='h-3.5 w-3.5 shrink-0 text-muted-foreground' /> : null}
              </Link>
            );
          })}
        </nav>

        <div className='shrink-0 space-y-3 pt-6'>
          <div
            className={cn(
              'flex items-center gap-2 rounded-md border border-border bg-background/60 px-3 py-2 text-sm',
              collapsed && 'lg:justify-center lg:px-0'
            )}
            title={displayName}
          >
            <UserCircle2 className='h-4 w-4 shrink-0 text-muted-foreground' />
            <div className={cn('flex min-w-0 items-center gap-2', collapsed && 'lg:hidden')}>
              <span className='truncate font-medium'>{displayName}</span>
              <SubscriptionBadge plan={effectivePlan} />
            </div>
          </div>
          <Button onClick={logout} disabled={loggingOut} variant='outline' className={cn('w-full', collapsed && 'lg:px-0')}>
            <span className={cn(collapsed && 'lg:hidden')}>{loggingOut ? 'Logging out...' : 'Logout'}</span>
            <span className={cn('hidden', collapsed && 'lg:inline')}>Logout</span>
          </Button>
        </div>
      </aside>

      {open ? (
        <button
          type='button'
          onClick={() => setOpen(false)}
          className='fixed inset-0 z-30 bg-black/30 lg:hidden'
          aria-label='Close sidebar overlay'
        />
      ) : null}

      <div className='flex min-h-screen flex-1 flex-col'>
        <header className='sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur'>
          <div className='flex items-center gap-3 px-4 py-3 sm:px-6'>
            <Button variant='ghost' size='icon' onClick={() => setOpen(true)} className='lg:hidden'>
              <Menu className='h-5 w-5' />
            </Button>
            <Button variant='ghost' size='icon' onClick={() => setCollapsed((prev) => !prev)} className='hidden lg:inline-flex'>
              <Menu className='h-5 w-5' />
            </Button>
            <h1 className='font-[var(--font-space)] text-lg font-semibold'>{title}</h1>
            <div className='mx-auto hidden w-full max-w-md md:block'>
              <Input placeholder='Search invoices, clients, GST numbers...' />
            </div>
            <Button variant='outline' size='icon'>
              <Bell className='h-4 w-4' />
            </Button>
          </div>
        </header>

        <main className='flex-1 px-4 py-5 sm:px-6'>{children}</main>
      </div>
    </div>
  );
}
