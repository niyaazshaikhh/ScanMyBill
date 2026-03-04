'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { BarChart3, Bell, CircleHelp, FileText, LayoutDashboard, Lock, Menu, PlusCircle, Settings, UserCircle2, Users, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { SubscriptionBadge } from '@/components/SubscriptionBadge';
import { Button } from '@/components/ui/button';
import { apiRequest } from '@/lib/api';
import { APP_NOTIFICATION_EVENT, type AppNotificationPayload } from '@/lib/app-notification';
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

type SearchInvoice = {
  id: string;
  invoice_number: string;
  client_name: string | null;
  gst_number: string | null;
  type: 'sales' | 'purchase';
};

type SearchClient = {
  id: string;
  name: string;
  email: string | null;
  gst_number: string | null;
};

type SearchDeliveryChallan = {
  id: string;
  challan_number: number;
  order_number: string;
  client_name: string | null;
};

type SearchSuggestion = {
  id: string;
  label: string;
  subtitle: string;
  href: string;
  section: 'Invoice' | 'Delivery Challan' | 'Client' | 'Settings';
};

type NotificationItem = {
  id: string;
  category: 'activity' | 'alert' | 'system';
  title: string;
  message: string;
  route: string | null;
  is_read: boolean;
  created_at: string;
};

type NotificationsResponse = {
  notifications: NotificationItem[];
  unread_count: number;
  count: number;
};

type ToastItem = {
  id: string;
  title: string;
  message: string;
  tone: 'info' | 'success' | 'error';
};

function formatNotificationTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const SETTINGS_SEARCH_TARGETS = [
  {
    id: 'settings-home',
    label: 'Settings',
    subtitle: 'Account and subscription settings',
    href: '/settings',
    keywords: ['settings', 'subscription', 'plan', 'account'],
  },
  {
    id: 'settings-personal-details',
    label: 'Personal Details',
    subtitle: 'Company, GST and bank setup',
    href: '/settings/personal_details',
    keywords: ['personal', 'details', 'company', 'gst', 'bank', 'ifsc', 'address'],
  },
] as const;

const ROUTE_SEARCH_TARGETS = [
  {
    id: 'route-invoices',
    label: 'Invoices',
    subtitle: 'Go to invoice explorer',
    href: '/invoices',
    section: 'Invoice' as const,
    keywords: ['invoice', 'invoices', 'bill', 'bills', 'gst'],
  },
  {
    id: 'route-delivery-challans',
    label: 'Delivery Challans',
    subtitle: 'Go to delivery challan explorer',
    href: '/invoices/delivery-challan',
    section: 'Delivery Challan' as const,
    keywords: ['delivery', 'challan', 'challans', 'non gst'],
  },
  {
    id: 'route-clients',
    label: 'Clients',
    subtitle: 'Go to client master list',
    href: '/clients',
    section: 'Client' as const,
    keywords: ['client', 'clients', 'customer', 'gst'],
  },
] as const;

function includesQuery(value: string | null | undefined, query: string): boolean {
  return (value || '').toLowerCase().includes(query);
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [displayName, setDisplayName] = useState('User');
  const [subscriptionPlan, setSubscriptionPlan] = useState<SubscriptionPlan>('FREE');
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionStatus>('EXPIRED');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchDataLoaded, setSearchDataLoaded] = useState(false);
  const [searchInvoices, setSearchInvoices] = useState<SearchInvoice[]>([]);
  const [searchClients, setSearchClients] = useState<SearchClient[]>([]);
  const [searchDeliveryChallans, setSearchDeliveryChallans] = useState<SearchDeliveryChallan[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [unreadNotificationCount, setUnreadNotificationCount] = useState(0);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const notificationsContainerRef = useRef<HTMLDivElement | null>(null);
  const seenNotificationIdsRef = useRef<Set<string>>(new Set());
  const initializedNotificationSyncRef = useRef(false);
  const toastTimersRef = useRef<Map<string, number>>(new Map());
  const notificationCloseTimerRef = useRef<number | null>(null);

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

  const loadSearchData = useCallback(async () => {
    if (searchLoading || searchDataLoaded) return;

    setSearchLoading(true);
    try {
      const [invoiceResult, clientResult, deliveryResult] = await Promise.allSettled([
        apiRequest<{ invoices: SearchInvoice[] }>('/invoices'),
        apiRequest<SearchClient[]>('/clients'),
        apiRequest<{ challans: SearchDeliveryChallan[] }>('/delivery-challans'),
      ]);

      if (invoiceResult.status === 'fulfilled') {
        setSearchInvoices(invoiceResult.value.invoices || []);
      } else {
        setSearchInvoices([]);
      }

      if (clientResult.status === 'fulfilled') {
        setSearchClients(clientResult.value || []);
      } else {
        setSearchClients([]);
      }

      if (deliveryResult.status === 'fulfilled') {
        setSearchDeliveryChallans(deliveryResult.value.challans || []);
      } else {
        setSearchDeliveryChallans([]);
      }
    } finally {
      setSearchDataLoaded(true);
      setSearchLoading(false);
    }
  }, [searchDataLoaded, searchLoading]);

  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setSearchOpen(false);
      return;
    }

    setSearchOpen(true);
    void loadSearchData();
  }, [loadSearchData, searchQuery]);

  useEffect(() => {
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (searchContainerRef.current && !searchContainerRef.current.contains(target)) {
        setSearchOpen(false);
      }
      if (notificationsContainerRef.current && !notificationsContainerRef.current.contains(target)) {
        setNotificationsOpen(false);
      }
    };

    window.addEventListener('mousedown', onMouseDown);
    return () => {
      window.removeEventListener('mousedown', onMouseDown);
    };
  }, []);

  const dismissToast = useCallback((toastId: string) => {
    setToasts((previous) => previous.filter((item) => item.id !== toastId));
    const timeoutId = toastTimersRef.current.get(toastId);
    if (timeoutId) {
      window.clearTimeout(timeoutId);
      toastTimersRef.current.delete(toastId);
    }
  }, []);

  const queueToast = useCallback((toast: ToastItem, durationMs = 5000) => {
    setToasts((previous) => {
      const withoutDuplicate = previous.filter((item) => item.id !== toast.id);
      return [...withoutDuplicate, toast].slice(-5);
    });

    const existingTimer = toastTimersRef.current.get(toast.id);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }
    const timeoutId = window.setTimeout(() => {
      dismissToast(toast.id);
    }, durationMs);
    toastTimersRef.current.set(toast.id, timeoutId);
  }, [dismissToast]);

  const pushToasts = useCallback((freshNotifications: NotificationItem[]) => {
    if (!freshNotifications.length) return;

    freshNotifications.forEach((notification) => {
      if (toastTimersRef.current.has(notification.id)) return;
      queueToast({
        id: notification.id,
        title: notification.title,
        message: notification.message,
        tone: notification.category === 'alert' ? 'error' : 'info',
      });
    });
  }, [queueToast]);

  useEffect(() => {
    const onAppNotification = (event: Event) => {
      const customEvent = event as CustomEvent<AppNotificationPayload>;
      const detail = customEvent.detail;
      if (!detail?.title) return;

      const toastId = detail.id || `local-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      queueToast(
        {
          id: toastId,
          title: detail.title,
          message: detail.message || '',
          tone: detail.tone || 'info',
        },
        detail.durationMs && detail.durationMs > 0 ? detail.durationMs : 5000,
      );
    };

    window.addEventListener(APP_NOTIFICATION_EVENT, onAppNotification as EventListener);
    return () => {
      window.removeEventListener(APP_NOTIFICATION_EVENT, onAppNotification as EventListener);
    };
  }, [queueToast]);

  const syncNotifications = useCallback(async (quiet = false) => {
    if (!getAuthToken()) {
      setNotifications([]);
      setUnreadNotificationCount(0);
      return;
    }

    if (!quiet) {
      setNotificationsLoading(true);
    }
    try {
      const response = await apiRequest<NotificationsResponse>('/notifications?limit=30');
      setNotifications(response.notifications || []);
      setUnreadNotificationCount(response.unread_count || 0);

      const incoming = response.notifications || [];
      if (!initializedNotificationSyncRef.current) {
        seenNotificationIdsRef.current = new Set(incoming.map((item) => item.id));
        initializedNotificationSyncRef.current = true;
        return;
      }

      const fresh = incoming.filter((item) => !seenNotificationIdsRef.current.has(item.id));
      if (fresh.length) {
        fresh.forEach((item) => seenNotificationIdsRef.current.add(item.id));
        pushToasts(fresh);
      }
    } catch {
      if (!quiet) {
        setNotifications([]);
        setUnreadNotificationCount(0);
      }
    } finally {
      if (!quiet) {
        setNotificationsLoading(false);
      }
    }
  }, [pushToasts]);

  useEffect(() => {
    void syncNotifications();
    const poll = window.setInterval(() => {
      void syncNotifications(true);
    }, 20000);

    return () => {
      window.clearInterval(poll);
    };
  }, [syncNotifications]);

  useEffect(() => {
    const timers = toastTimersRef.current;
    return () => {
      timers.forEach((timeoutId) => window.clearTimeout(timeoutId));
      timers.clear();
      if (notificationCloseTimerRef.current) {
        window.clearTimeout(notificationCloseTimerRef.current);
        notificationCloseTimerRef.current = null;
      }
    };
  }, []);

  const markAllNotificationsAsRead = useCallback(async () => {
    if (unreadNotificationCount <= 0) return;

    setNotifications((previous) => previous.map((item) => ({ ...item, is_read: true })));
    setUnreadNotificationCount(0);

    try {
      await apiRequest('/notifications/read-all', { method: 'POST' });
    } catch {
      void syncNotifications(true);
    }
  }, [syncNotifications, unreadNotificationCount]);

  const clearAllNotifications = useCallback(async () => {
    if (notifications.length <= 0) return;

    const previousNotifications = notifications;
    const previousUnreadCount = unreadNotificationCount;
    const previousToasts = toasts;

    setNotifications([]);
    setUnreadNotificationCount(0);
    setToasts([]);
    seenNotificationIdsRef.current = new Set();
    toastTimersRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    toastTimersRef.current.clear();

    try {
      await apiRequest('/notifications/clear-all', { method: 'DELETE' });
    } catch {
      setNotifications(previousNotifications);
      setUnreadNotificationCount(previousUnreadCount);
      setToasts(previousToasts);
      previousNotifications.forEach((notification) => {
        seenNotificationIdsRef.current.add(notification.id);
      });
      void syncNotifications(true);
    }
  }, [notifications, unreadNotificationCount, toasts, syncNotifications]);

  const openNotification = useCallback(async (notification: NotificationItem) => {
    setNotificationsOpen(false);

    if (!notification.is_read) {
      setNotifications((previous) =>
        previous.map((item) => (item.id === notification.id ? { ...item, is_read: true } : item)),
      );
      setUnreadNotificationCount((previous) => Math.max(previous - 1, 0));
      try {
        await apiRequest(`/notifications/${notification.id}/read`, { method: 'POST' });
      } catch {
        void syncNotifications(true);
      }
    }

    if (notification.route) {
      router.push(notification.route);
    }
  }, [router, syncNotifications]);

  const searchSuggestions = useMemo<SearchSuggestion[]>(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return [];

    const invoiceSuggestions = searchInvoices
      .filter((invoice) =>
        includesQuery(invoice.invoice_number, query)
        || includesQuery(invoice.client_name, query)
        || includesQuery(invoice.gst_number, query)
      )
      .slice(0, 4)
      .map((invoice) => ({
        id: `invoice-${invoice.id}`,
        label: `Invoice ${invoice.invoice_number}`,
        subtitle: `${invoice.client_name || 'Unlinked'} • ${invoice.type}`,
        href: '/invoices',
        section: 'Invoice' as const,
      }));

    const deliverySuggestions = searchDeliveryChallans
      .filter((challan) =>
        includesQuery(String(challan.challan_number), query)
        || includesQuery(challan.order_number, query)
        || includesQuery(challan.client_name, query)
      )
      .slice(0, 4)
      .map((challan) => ({
        id: `delivery-${challan.id}`,
        label: `Delivery Challan ${challan.challan_number}`,
        subtitle: `Order ${challan.order_number}${challan.client_name ? ` • ${challan.client_name}` : ''}`,
        href: '/invoices/delivery-challan',
        section: 'Delivery Challan' as const,
      }));

    const clientSuggestions = searchClients
      .filter((client) =>
        includesQuery(client.name, query)
        || includesQuery(client.gst_number, query)
        || includesQuery(client.email, query)
      )
      .slice(0, 4)
      .map((client) => ({
        id: `client-${client.id}`,
        label: client.name,
        subtitle: client.gst_number || client.email || 'Client',
        href: '/clients',
        section: 'Client' as const,
      }));

    const settingsSuggestions = SETTINGS_SEARCH_TARGETS
      .filter((target) =>
        includesQuery(target.label, query)
        || includesQuery(target.subtitle, query)
        || target.keywords.some((keyword) => keyword.includes(query))
      )
      .map((target) => ({
        id: target.id,
        label: target.label,
        subtitle: target.subtitle,
        href: target.href,
        section: 'Settings' as const,
      }));

    const routeSuggestions = ROUTE_SEARCH_TARGETS
      .filter((target) =>
        includesQuery(target.label, query)
        || includesQuery(target.subtitle, query)
        || target.keywords.some((keyword) => keyword.includes(query))
      )
      .map((target) => ({
        id: target.id,
        label: target.label,
        subtitle: target.subtitle,
        href: target.href,
        section: target.section,
      }));

    const deduped = new Map<string, SearchSuggestion>();
    [...routeSuggestions, ...invoiceSuggestions, ...deliverySuggestions, ...clientSuggestions, ...settingsSuggestions].forEach(
      (item) => {
        if (!deduped.has(item.id)) {
          deduped.set(item.id, item);
        }
      },
    );

    return Array.from(deduped.values()).slice(0, 10);
  }, [searchClients, searchDeliveryChallans, searchInvoices, searchQuery]);

  const goToSearchTarget = useCallback((href: string) => {
    setSearchQuery('');
    setSearchOpen(false);
    router.push(href);
  }, [router]);

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
    <div className='flex h-screen overflow-hidden'>
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 min-h-0 flex-col border-r border-border bg-white/95 p-4 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
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

      <div className='flex h-screen min-h-0 flex-1 flex-col overflow-y-auto'>
        <header className='sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur'>
          <div className='flex items-center gap-3 px-4 py-3 sm:px-6'>
            <Button variant='ghost' size='icon' onClick={() => setOpen(true)} className='lg:hidden'>
              <Menu className='h-5 w-5' />
            </Button>
            <Button variant='ghost' size='icon' onClick={() => setCollapsed((prev) => !prev)} className='hidden lg:inline-flex'>
              <Menu className='h-5 w-5' />
            </Button>
            <h1 className='font-[var(--font-space)] text-lg font-semibold'>{title}</h1>
            <div ref={searchContainerRef} className='mx-auto hidden w-full max-w-md md:block'>
              <div className='relative'>
                <Input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onFocus={() => {
                    if (searchQuery.trim()) {
                      setSearchOpen(true);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      setSearchOpen(false);
                      return;
                    }
                    if (event.key === 'Enter' && searchSuggestions.length > 0) {
                      event.preventDefault();
                      goToSearchTarget(searchSuggestions[0].href);
                    }
                  }}
                  placeholder='Search invoices, clients, GST numbers...'
                />
                {searchOpen ? (
                  <div className='absolute left-0 right-0 top-[calc(100%+6px)] z-50 max-h-80 overflow-y-auto rounded-md border border-border bg-background shadow-lg'>
                    {searchLoading ? (
                      <p className='px-3 py-2 text-sm text-muted-foreground'>Searching...</p>
                    ) : searchSuggestions.length === 0 ? (
                      <p className='px-3 py-2 text-sm text-muted-foreground'>No matches found.</p>
                    ) : (
                      <ul className='py-1'>
                        {searchSuggestions.map((suggestion) => (
                          <li key={suggestion.id}>
                            <button
                              type='button'
                              className='flex w-full items-start justify-between gap-3 px-3 py-2 text-left hover:bg-muted'
                              onClick={() => goToSearchTarget(suggestion.href)}
                            >
                              <span className='min-w-0'>
                                <span className='block truncate text-sm font-medium text-foreground'>{suggestion.label}</span>
                                <span className='block truncate text-xs text-muted-foreground'>{suggestion.subtitle}</span>
                              </span>
                              <span className='shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground'>
                                {suggestion.section}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
            <div className='group relative'>
              <div
                className='inline-flex h-10 w-10 items-center justify-center rounded-md border border-input bg-background text-foreground'
                aria-label='Support'
                title='Need help? Hover for support details'
              >
                <CircleHelp className='h-4 w-4' />
              </div>
              <div className='pointer-events-none absolute right-0 top-full z-50 w-72 rounded-md border border-border bg-background p-3 text-xs text-muted-foreground opacity-0 shadow-lg transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100'>
                <p className='text-[11px] font-semibold uppercase tracking-wide text-foreground'>Need help?</p>
                <p className='mt-1'>
                  Support email:{' '}
                  <a className='font-medium text-primary hover:underline' href='mailto:support@scanmybill.in'>
                    support@scanmybill.in
                  </a>
                </p>
                <p className='mt-2'>
                  Developer:{' '}
                  <a className='font-medium text-primary hover:underline' href='https://www.linkedin.com/in/niyaazshaikhh/'>
                    Niyaz Shaikh
                  </a>
                </p>
                <div className='mt-2 flex flex-wrap gap-2'>
                  <a className='rounded border border-border px-2 py-1 text-primary hover:bg-muted' href='https://x.com/niyaazshaikhh'>
                    X
                  </a>
                  <a className='rounded border border-border px-2 py-1 text-primary hover:bg-muted' href='https://www.linkedin.com/in/niyaazshaikhh/'>
                    LinkedIn
                  </a>
                  <a className='rounded border border-border px-2 py-1 text-primary hover:bg-muted' href='https://www.instagram.com/whyniyaaz/'>
                    Instagram
                  </a>
                </div>
              </div>
            </div>
            <div
              ref={notificationsContainerRef}
              className='relative'
              onMouseEnter={() => {
                if (notificationCloseTimerRef.current) {
                  window.clearTimeout(notificationCloseTimerRef.current);
                  notificationCloseTimerRef.current = null;
                }
                if (!notificationsOpen) {
                  void syncNotifications(true);
                }
                setNotificationsOpen(true);
              }}
              onMouseLeave={() => {
                notificationCloseTimerRef.current = window.setTimeout(() => {
                  setNotificationsOpen(false);
                  notificationCloseTimerRef.current = null;
                }, 180);
              }}
            >
              <Button
                variant='outline'
                size='icon'
                onClick={() => {
                  const next = !notificationsOpen;
                  setNotificationsOpen(next);
                  if (next) {
                    void syncNotifications(true);
                  }
                }}
                className='relative'
                aria-label='Notifications'
                title='Notifications'
              >
                <Bell className='h-4 w-4' />
                {unreadNotificationCount > 0 ? (
                  <span className='absolute -right-1 -top-1 grid min-h-5 min-w-5 place-items-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground'>
                    {unreadNotificationCount > 99 ? '99+' : unreadNotificationCount}
                  </span>
                ) : null}
              </Button>
              {notificationsOpen ? (
                <div className='absolute right-0 top-full z-50 w-96 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-border bg-background shadow-lg'>
                  <div className='flex items-center justify-between border-b border-border px-3 py-2'>
                    <p className='text-sm font-semibold text-foreground'>Notifications</p>
                    <div className='flex items-center gap-3'>
                      <button
                        type='button'
                        className='text-xs text-muted-foreground hover:text-foreground disabled:opacity-60'
                        onClick={() => void markAllNotificationsAsRead()}
                        disabled={unreadNotificationCount <= 0}
                      >
                        Mark all read
                      </button>
                      <button
                        type='button'
                        className='text-xs text-muted-foreground hover:text-foreground disabled:opacity-60'
                        onClick={() => void clearAllNotifications()}
                        disabled={notifications.length <= 0}
                      >
                        Clear all
                      </button>
                    </div>
                  </div>
                  <div className='max-h-80 overflow-y-auto'>
                    {notificationsLoading ? (
                      <p className='px-3 py-2 text-sm text-muted-foreground'>Loading notifications...</p>
                    ) : notifications.length === 0 ? (
                      <p className='px-3 py-2 text-sm text-muted-foreground'>No notifications yet.</p>
                    ) : (
                      <ul className='py-1'>
                        {notifications.map((notification) => (
                          <li key={notification.id}>
                            <button
                              type='button'
                              className={cn(
                                'flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-muted',
                                !notification.is_read && 'bg-muted/40'
                              )}
                              onClick={() => void openNotification(notification)}
                            >
                              <span
                                className={cn(
                                  'mt-1 h-2 w-2 shrink-0 rounded-full bg-primary/80',
                                  notification.is_read && 'opacity-0'
                                )}
                                aria-hidden={notification.is_read}
                              />
                              <span className='min-w-0 flex-1'>
                                <span className='block truncate text-sm font-medium text-foreground'>{notification.title}</span>
                                <span className='block text-xs text-muted-foreground'>{notification.message}</span>
                                <span className='mt-1 block text-[11px] text-muted-foreground'>
                                  {formatNotificationTimestamp(notification.created_at)}
                                </span>
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className='flex-1 px-4 py-5 sm:px-6'>{children}</main>
      </div>
      <div className='pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-1.5rem))] flex-col gap-2'>
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'pointer-events-auto rounded-md border shadow-lg',
              toast.tone === 'success' && 'border-emerald-300 bg-emerald-50',
              toast.tone === 'error' && 'border-red-300 bg-red-50',
              toast.tone === 'info' && 'border-border bg-background',
            )}
          >
            <div className='flex items-start gap-2 p-3'>
              <div className='min-w-0 flex-1'>
                <p className={cn('text-sm font-semibold', toast.tone === 'success' ? 'text-emerald-900' : 'text-foreground')}>
                  {toast.title}
                </p>
                <p className={cn('text-xs', toast.tone === 'success' ? 'text-emerald-800' : 'text-muted-foreground')}>
                  {toast.message}
                </p>
              </div>
              <button
                type='button'
                onClick={() => dismissToast(toast.id)}
                className={cn(
                  'rounded p-1 hover:text-foreground',
                  toast.tone === 'success' ? 'text-emerald-700 hover:bg-emerald-100' : 'text-muted-foreground hover:bg-muted',
                )}
                aria-label='Close notification'
              >
                <X className='h-3.5 w-3.5' />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
