'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PopupWindow } from '@/components/ui/popup-window';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import { getAuthUser } from '@/lib/auth';
import { showAppErrorPopup, showAppInfoPopup, showAppSuccessPopup } from '@/lib/app-popup';

export const dynamic = 'force-dynamic';

type NewsletterSubscriber = {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
};

type NewsletterUserTarget = {
  id: string;
  full_name: string;
  email: string;
  role: 'admin' | 'user';
  is_active: boolean;
  notifications_enabled: boolean;
  created_at: string;
};

type NewsletterSubscribersResponse = {
  total_subscribers: number;
  active_subscribers: number;
  subscribers: NewsletterSubscriber[];
};

type NewsletterUsersResponse = {
  total_users: number;
  active_users: number;
  users: NewsletterUserTarget[];
};

type NewsletterSendResponse = {
  success: boolean;
  message: string;
  attempted: number;
  sent: number;
  failed: number;
  queued_notifications: number;
  failed_recipients: string[];
};

export default function NewsletterPage() {
  useAuthGuard();

  const router = useRouter();
  const [subscriberSearch, setSubscriberSearch] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [loadingSubscribers, setLoadingSubscribers] = useState(true);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [sending, setSending] = useState(false);
  const [deletingSubscriberId, setDeletingSubscriberId] = useState<string | null>(null);
  const [pendingDeleteSubscriber, setPendingDeleteSubscriber] = useState<NewsletterSubscriber | null>(null);
  const [subscribers, setSubscribers] = useState<NewsletterSubscriber[]>([]);
  const [users, setUsers] = useState<NewsletterUserTarget[]>([]);
  const [selectedSubscriberIds, setSelectedSubscriberIds] = useState<Set<string>>(new Set());
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());
  const [sendEmail, setSendEmail] = useState(true);
  const [sendNotifications, setSendNotifications] = useState(false);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');

  const isAdminUser = getAuthUser()?.role === 'admin';

  useEffect(() => {
    if (!isAdminUser) {
      router.replace('/dashboard');
    }
  }, [isAdminUser, router]);

  const loadSubscribers = async (searchTerm = '') => {
    setLoadingSubscribers(true);
    try {
      const query = searchTerm.trim() ? `?search=${encodeURIComponent(searchTerm.trim())}` : '';
      const data = await apiRequest<NewsletterSubscribersResponse>(`/admin/newsletter/subscribers${query}`);
      setSubscribers(data.subscribers || []);
      setSelectedSubscriberIds(new Set());
    } catch {
      setSubscribers([]);
    } finally {
      setLoadingSubscribers(false);
    }
  };

  const loadUsers = async (searchTerm = '') => {
    setLoadingUsers(true);
    try {
      const query = searchTerm.trim() ? `?search=${encodeURIComponent(searchTerm.trim())}` : '';
      const data = await apiRequest<NewsletterUsersResponse>(`/admin/newsletter/users${query}`);
      setUsers(data.users || []);
      setSelectedUserIds(new Set());
    } catch {
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (!isAdminUser) return;
    const timeout = window.setTimeout(() => {
      void loadSubscribers(subscriberSearch);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [isAdminUser, subscriberSearch]);

  useEffect(() => {
    if (!isAdminUser) return;
    const timeout = window.setTimeout(() => {
      void loadUsers(userSearch);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [isAdminUser, userSearch]);

  const selectableSubscribers = useMemo(
    () => subscribers.filter((subscriber) => subscriber.is_active),
    [subscribers],
  );
  const selectableUsers = useMemo(
    () => users.filter((user) => user.is_active),
    [users],
  );

  const selectedSubscriberCount = selectedSubscriberIds.size;
  const selectedUserCount = selectedUserIds.size;
  const canSendEmail = selectedSubscriberCount > 0 || selectedUserCount > 0;
  const canSendNotifications = selectedUserCount > 0;
  const shouldScrollSubscribers = subscribers.length > 4;
  const shouldScrollUsers = users.length > 4;
  const allSubscribersSelected =
    selectableSubscribers.length > 0 && selectedSubscriberCount === selectableSubscribers.length;
  const allUsersSelected = selectableUsers.length > 0 && selectedUserCount === selectableUsers.length;

  const emailRecipientCount = useMemo(() => {
    const emails = new Set<string>();
    subscribers.forEach((subscriber) => {
      if (subscriber.is_active && selectedSubscriberIds.has(subscriber.id)) {
        emails.add(subscriber.email.trim().toLowerCase());
      }
    });
    users.forEach((user) => {
      if (user.is_active && selectedUserIds.has(user.id)) {
        emails.add(user.email.trim().toLowerCase());
      }
    });
    return emails.size;
  }, [selectedSubscriberIds, selectedUserIds, subscribers, users]);

  const notificationTargetCount = useMemo(
    () =>
      users.filter(
        (user) => user.is_active && user.notifications_enabled && selectedUserIds.has(user.id),
      ).length,
    [selectedUserIds, users],
  );

  const canQueueSend =
    (sendEmail && emailRecipientCount > 0) || (sendNotifications && selectedUserCount > 0);

  useEffect(() => {
    if (!canSendEmail && sendEmail) {
      setSendEmail(false);
      return;
    }
    if (!canSendNotifications && sendNotifications) {
      setSendNotifications(false);
      return;
    }
    if (canSendEmail && !canSendNotifications && !sendEmail) {
      setSendEmail(true);
      return;
    }
    if (canSendEmail && canSendNotifications && !sendEmail && !sendNotifications) {
      setSendEmail(true);
    }
  }, [canSendEmail, canSendNotifications, sendEmail, sendNotifications]);

  const toggleSelectAllSubscribers = () => {
    if (allSubscribersSelected) {
      setSelectedSubscriberIds(new Set());
      return;
    }

    setSelectedSubscriberIds(new Set(selectableSubscribers.map((subscriber) => subscriber.id)));
  };

  const toggleSelectAllUsers = () => {
    if (allUsersSelected) {
      setSelectedUserIds(new Set());
      return;
    }

    setSelectedUserIds(new Set(selectableUsers.map((user) => user.id)));
  };

  const toggleSubscriberSelection = (subscriberId: string) => {
    setSelectedSubscriberIds((previous) => {
      const next = new Set(previous);
      if (next.has(subscriberId)) {
        next.delete(subscriberId);
      } else {
        next.add(subscriberId);
      }
      return next;
    });
  };

  const toggleUserSelection = (userId: string) => {
    setSelectedUserIds((previous) => {
      const next = new Set(previous);
      if (next.has(userId)) {
        next.delete(userId);
      } else {
        next.add(userId);
      }
      return next;
    });
  };

  const sendNewsletter = async () => {
    const trimmedSubject = subject.trim();
    const trimmedMessage = message.trim();

    if (!sendEmail && !sendNotifications) {
      showAppErrorPopup('Select at least one delivery option.', 'Validation Error');
      return;
    }
    if (sendEmail && emailRecipientCount <= 0) {
      showAppErrorPopup('Select at least one subscriber or user for email delivery.', 'Validation Error');
      return;
    }
    if (sendNotifications && selectedUserCount <= 0) {
      showAppErrorPopup('Select at least one user to send notifications.', 'Validation Error');
      return;
    }
    if (trimmedSubject.length < 3) {
      showAppErrorPopup('Subject should be at least 3 characters.', 'Validation Error');
      return;
    }
    if (trimmedMessage.length < 5) {
      showAppErrorPopup('Message should be at least 5 characters.', 'Validation Error');
      return;
    }

    setSending(true);
    try {
      const response = await apiRequest<NewsletterSendResponse>('/admin/newsletter/send', {
        method: 'POST',
        body: {
          subscriber_ids: Array.from(selectedSubscriberIds),
          user_ids: Array.from(selectedUserIds),
          send_email: sendEmail,
          send_notifications: sendNotifications,
          subject: trimmedSubject,
          message: trimmedMessage,
        },
      });

      if (response.failed > 0) {
        showAppInfoPopup(
          `${response.message}. Failed: ${response.failed_recipients.join(', ')}`,
          'Dispatch Result',
        );
      } else {
        showAppSuccessPopup(response.message, 'Dispatch Queued');
      }
      setMessage('');
      setSelectedSubscriberIds(new Set());
      setSelectedUserIds(new Set());
    } catch {
      // API layer popup handles errors.
    } finally {
      setSending(false);
    }
  };

  const deleteSubscriber = async (subscriber: NewsletterSubscriber) => {
    setDeletingSubscriberId(subscriber.id);
    try {
      await apiRequest(`/admin/newsletter/subscribers/${encodeURIComponent(subscriber.id)}`, {
        method: 'DELETE',
      });
      setSelectedSubscriberIds((previous) => {
        const next = new Set(previous);
        next.delete(subscriber.id);
        return next;
      });
      showAppSuccessPopup(`${subscriber.email} deleted from newsletter list.`, 'Subscriber Deleted');
      await loadSubscribers(subscriberSearch);
    } catch {
      // API layer popup handles errors.
    } finally {
      setDeletingSubscriberId(null);
    }
  };

  const confirmDeleteSubscriber = () => {
    if (!pendingDeleteSubscriber) return;
    const targetSubscriber = pendingDeleteSubscriber;
    setPendingDeleteSubscriber(null);
    void deleteSubscriber(targetSubscriber);
  };

  return (
    <div className='space-y-5'>
      <div>
        <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Newsletter and Notifications</h2>
        <p className='text-sm text-muted-foreground'>
          Manage newsletter subscribers and users, then send emails and in-app notifications together.
        </p>
      </div>

      <Card className='bg-card/90'>
        <CardHeader>
          <CardTitle>Compose Email and Send in-app Notification</CardTitle>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='space-y-1'>
            <Label htmlFor='newsletter-subject'>Subject</Label>
            <Input
              id='newsletter-subject'
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              maxLength={180}
              placeholder='Enter email/notification subject'
            />
          </div>
          <div className='space-y-1'>
            <Label htmlFor='newsletter-message'>Message</Label>
            <Textarea
              id='newsletter-message'
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              maxLength={10000}
              rows={8}
              placeholder='Write the message for both email and in-app notification'
            />
          </div>
          <div className='grid gap-2 rounded-md border p-3 text-sm sm:grid-cols-2'>
            <label className={`flex items-center gap-2 ${canSendEmail ? '' : 'opacity-60'}`}>
              <input
                type='checkbox'
                checked={sendEmail}
                onChange={(event) => setSendEmail(event.target.checked)}
                disabled={!canSendEmail}
                className='h-4 w-4'
              />
              Send email to selected subscribers and users ({emailRecipientCount})
            </label>
            <label className={`flex items-center gap-2 ${canSendNotifications ? '' : 'opacity-60'}`}>
              <input
                type='checkbox'
                checked={sendNotifications}
                onChange={(event) => setSendNotifications(event.target.checked)}
                disabled={!canSendNotifications}
                className='h-4 w-4'
              />
              Send in-app notifications to selected users ({notificationTargetCount})
            </label>
          </div>
          <div className='flex justify-end'>
            <Button type='button' onClick={() => void sendNewsletter()} disabled={sending || !canQueueSend}>
              {sending ? 'Sending...' : 'Queue Email and Notification'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className='bg-card/90'>
        <CardHeader className='flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between'>
          <CardTitle>Newsletter Subscribers</CardTitle>
          <div className='relative w-full sm:w-72'>
            <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              value={subscriberSearch}
              onChange={(event) => setSubscriberSearch(event.target.value)}
              placeholder='Search by email'
              className='pl-9'
            />
          </div>
        </CardHeader>
        <CardContent className='space-y-4'>
          <p className='text-xs text-muted-foreground'>
            Selected subscribers: {selectedSubscriberCount} of {selectableSubscribers.length}
          </p>
          {loadingSubscribers ? <p className='text-sm text-muted-foreground'>Loading newsletter subscribers...</p> : null}
          {!loadingSubscribers ? (
            <div className={`rounded-md border ${shouldScrollSubscribers ? 'max-h-[320px] overflow-y-auto' : ''}`}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='w-[64px]'>
                      <input
                        type='checkbox'
                        checked={allSubscribersSelected}
                        onChange={toggleSelectAllSubscribers}
                        disabled={selectableSubscribers.length === 0}
                        aria-label='Select all newsletter subscribers'
                        className='h-4 w-4'
                      />
                    </TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className='text-right'>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {subscribers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className='text-center text-muted-foreground'>
                        No newsletter subscribers found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    subscribers.map((subscriber) => (
                      <TableRow key={subscriber.id}>
                        <TableCell>
                          <input
                            type='checkbox'
                            checked={selectedSubscriberIds.has(subscriber.id)}
                            onChange={() => toggleSubscriberSelection(subscriber.id)}
                            disabled={!subscriber.is_active}
                            aria-label={`Select ${subscriber.email}`}
                            className='h-4 w-4'
                          />
                        </TableCell>
                        <TableCell className='font-medium'>{subscriber.email}</TableCell>
                        <TableCell>
                          <span className={subscriber.is_active ? 'text-emerald-700 dark:text-emerald-300' : 'text-muted-foreground'}>
                            {subscriber.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </TableCell>
                        <TableCell className='text-right'>
                          <Button
                            type='button'
                            variant='destructive'
                            size='sm'
                            onClick={() => setPendingDeleteSubscriber(subscriber)}
                            disabled={deletingSubscriberId === subscriber.id}
                          >
                            {deletingSubscriberId === subscriber.id ? 'Deleting...' : 'Delete'}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className='bg-card/90'>
        <CardHeader className='flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between'>
          <CardTitle>Users</CardTitle>
          <div className='relative w-full sm:w-72'>
            <Search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
            <Input
              value={userSearch}
              onChange={(event) => setUserSearch(event.target.value)}
              placeholder='Search by name or email'
              className='pl-9'
            />
          </div>
        </CardHeader>
        <CardContent className='space-y-4'>
          <p className='text-xs text-muted-foreground'>
            Selected users: {selectedUserCount} of {selectableUsers.length}
          </p>
          {loadingUsers ? <p className='text-sm text-muted-foreground'>Loading users list...</p> : null}
          {!loadingUsers ? (
            <div className={`rounded-md border ${shouldScrollUsers ? 'max-h-[320px] overflow-y-auto' : ''}`}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='w-[64px]'>
                      <input
                        type='checkbox'
                        checked={allUsersSelected}
                        onChange={toggleSelectAllUsers}
                        disabled={selectableUsers.length === 0}
                        aria-label='Select all users'
                        className='h-4 w-4'
                      />
                    </TableHead>
                    <TableHead>User</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Notifications</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className='text-center text-muted-foreground'>
                        No users found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    users.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell>
                          <input
                            type='checkbox'
                            checked={selectedUserIds.has(user.id)}
                            onChange={() => toggleUserSelection(user.id)}
                            disabled={!user.is_active}
                            aria-label={`Select ${user.email}`}
                            className='h-4 w-4'
                          />
                        </TableCell>
                        <TableCell className='font-medium'>{user.full_name || user.role}</TableCell>
                        <TableCell>{user.email}</TableCell>
                        <TableCell>
                          <span className={user.notifications_enabled ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}>
                            {user.notifications_enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className={user.is_active ? 'text-emerald-700 dark:text-emerald-300' : 'text-muted-foreground'}>
                            {user.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <PopupWindow
        open={Boolean(pendingDeleteSubscriber)}
        title='Delete Subscriber'
        message={
          pendingDeleteSubscriber
            ? `Delete ${pendingDeleteSubscriber.email} from newsletter subscribers? This action cannot be undone.`
            : ''
        }
        confirmLabel='Delete'
        cancelLabel='Cancel'
        confirmVariant='destructive'
        onCancel={() => setPendingDeleteSubscriber(null)}
        onConfirm={confirmDeleteSubscriber}
      />
    </div>
  );
}

