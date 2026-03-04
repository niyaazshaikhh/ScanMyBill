'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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

type NewsletterSubscribersResponse = {
  total_subscribers: number;
  active_subscribers: number;
  subscribers: NewsletterSubscriber[];
};

type NewsletterSendResponse = {
  success: boolean;
  message: string;
  attempted: number;
  sent: number;
  failed: number;
  failed_recipients: string[];
};

export default function NewsletterPage() {
  useAuthGuard();

  const router = useRouter();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [subscribers, setSubscribers] = useState<NewsletterSubscriber[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');

  const isAdminUser = getAuthUser()?.role === 'admin';

  useEffect(() => {
    if (!isAdminUser) {
      router.replace('/dashboard');
    }
  }, [isAdminUser, router]);

  const loadSubscribers = async (searchTerm = '') => {
    setLoading(true);
    try {
      const query = searchTerm.trim() ? `?search=${encodeURIComponent(searchTerm.trim())}` : '';
      const data = await apiRequest<NewsletterSubscribersResponse>(`/admin/newsletter/subscribers${query}`);
      setSubscribers(data.subscribers || []);
      setSelectedIds(new Set());
    } catch {
      setSubscribers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdminUser) return;
    void loadSubscribers();
  }, [isAdminUser]);

  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadSubscribers(search);
  };

  const resetSearch = () => {
    setSearch('');
    void loadSubscribers('');
  };

  const selectableSubscribers = useMemo(
    () => subscribers.filter((subscriber) => subscriber.is_active),
    [subscribers],
  );
  const selectedCount = selectedIds.size;
  const allSelected = selectableSubscribers.length > 0 && selectedCount === selectableSubscribers.length;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
      return;
    }

    setSelectedIds(new Set(selectableSubscribers.map((subscriber) => subscriber.id)));
  };

  const toggleSelection = (subscriberId: string) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(subscriberId)) {
        next.delete(subscriberId);
      } else {
        next.add(subscriberId);
      }
      return next;
    });
  };

  const sendNewsletter = async () => {
    const trimmedSubject = subject.trim();
    const trimmedMessage = message.trim();

    if (selectedCount <= 0) {
      showAppErrorPopup('Select at least one email.', 'Validation Error');
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
          subscriber_ids: Array.from(selectedIds),
          subject: trimmedSubject,
          message: trimmedMessage,
        },
      });

      if (response.failed > 0) {
        showAppInfoPopup(
          `${response.message}. Failed: ${response.failed_recipients.join(', ')}`,
          'Newsletter Result',
        );
      } else {
        showAppSuccessPopup(response.message, 'Newsletter Sent');
      }
      setMessage('');
      setSelectedIds(new Set());
    } catch {
      // API layer popup handles errors.
    } finally {
      setSending(false);
    }
  };

  return (
    <div className='space-y-5'>
      <div>
        <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Newsletter</h2>
        <p className='text-sm text-muted-foreground'>
          View subscriber emails, select recipients, and send a message.
        </p>
      </div>

      <Card className='bg-white/90'>
        <CardHeader>
          <CardTitle>Compose Email</CardTitle>
        </CardHeader>
        <CardContent className='space-y-3'>
          <div className='space-y-1'>
            <Label htmlFor='newsletter-subject'>Subject</Label>
            <Input
              id='newsletter-subject'
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              maxLength={180}
              placeholder='Enter email subject'
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
              placeholder='Write your newsletter message here'
            />
          </div>
          <div className='flex justify-end'>
            <Button type='button' onClick={() => void sendNewsletter()} disabled={sending || selectedCount <= 0}>
              {sending ? 'Sending...' : `Send to ${selectedCount} selected`}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className='bg-white/90'>
        <CardHeader className='space-y-3'>
          <CardTitle>Subscribers</CardTitle>
          <form className='flex flex-col gap-2 sm:flex-row' onSubmit={submitSearch}>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder='Search by email'
            />
            <Button type='submit' disabled={loading}>
              Search
            </Button>
            <Button type='button' variant='outline' onClick={resetSearch} disabled={loading}>
              Reset
            </Button>
            <Button type='button' variant='outline' onClick={toggleSelectAll} disabled={selectableSubscribers.length === 0}>
              {allSelected ? 'Unselect all' : 'Select all'}
            </Button>
          </form>
        </CardHeader>
        <CardContent className='space-y-4'>
          <p className='text-xs text-muted-foreground'>
            Selected: {selectedCount} of {selectableSubscribers.length}
          </p>
          {loading ? <p className='text-sm text-muted-foreground'>Loading subscriber emails...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className='w-[64px]'>Select</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subscribers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className='text-center text-muted-foreground'>
                      No newsletter subscribers found.
                    </TableCell>
                  </TableRow>
                ) : (
                  subscribers.map((subscriber) => (
                    <TableRow key={subscriber.id}>
                      <TableCell>
                        <input
                          type='checkbox'
                          checked={selectedIds.has(subscriber.id)}
                          onChange={() => toggleSelection(subscriber.id)}
                          disabled={!subscriber.is_active}
                          aria-label={`Select ${subscriber.email}`}
                          className='h-4 w-4'
                        />
                      </TableCell>
                      <TableCell className='font-medium'>{subscriber.email}</TableCell>
                      <TableCell>
                        <span className={subscriber.is_active ? 'text-emerald-700' : 'text-muted-foreground'}>
                          {subscriber.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
