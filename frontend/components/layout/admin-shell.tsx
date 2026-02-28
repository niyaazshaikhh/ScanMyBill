'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Bell, FileText, LayoutDashboard, Menu, PlusCircle, Settings, Users, X } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { clearAuthSession } from '@/lib/auth';
import { cn } from '@/lib/utils';

const nav = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/invoices', label: 'Invoices', icon: FileText },
  { href: '/clients', label: 'Clients', icon: Users },
  { href: '/create', label: 'Create', icon: PlusCircle },
  { href: '/settings', label: 'Settings', icon: Settings }
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const title = useMemo(() => {
    return nav.find((item) => pathname.startsWith(item.href))?.label || 'Dashboard';
  }, [pathname]);

  const logout = () => {
    clearAuthSession();
    router.push('/signin');
  };

  return (
    <div className='flex min-h-screen'>
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-64 border-r border-border bg-white/95 p-4 transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
          collapsed && 'lg:w-20'
        )}
      >
        <div className='mb-6 flex items-center justify-between'>
          <Link href='/dashboard' className={cn('font-[var(--font-space)] text-xl font-semibold text-primary', collapsed && 'lg:hidden')}>
            ScanMyBill.in
          </Link>
          <Button variant='ghost' size='icon' className='lg:hidden' onClick={() => setOpen(false)}>
            <X className='h-5 w-5' />
          </Button>
        </div>

        <nav className='space-y-1'>
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition hover:bg-muted',
                  active && 'bg-secondary text-secondary-foreground',
                  collapsed && 'lg:justify-center'
                )}
                onClick={() => setOpen(false)}
              >
                <Icon className='h-4 w-4 shrink-0' />
                <span className={cn(collapsed && 'lg:hidden')}>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className='mt-8'>
          <Button onClick={logout} variant='outline' className={cn('w-full', collapsed && 'lg:px-0')}>
            <span className={cn(collapsed && 'lg:hidden')}>Sign Out</span>
            <span className={cn('hidden', collapsed && 'lg:inline')}>Out</span>
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