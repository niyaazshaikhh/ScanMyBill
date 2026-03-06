'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { getApiBaseUrl } from '@/lib/api';

type NewsletterSubscribeResponse = {
  success?: boolean;
  message?: string;
  detail?: string;
};

export function NewsletterForm() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loading) return;

    setLoading(true);
    setSuccessMessage(null);
    setErrorMessage(null);

    try {
      const res = await fetch(`${getApiBaseUrl()}/newsletter/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = (await res.json()) as NewsletterSubscribeResponse;
      const message = data.message || (typeof data.detail === 'string' ? data.detail : undefined);

      if (!res.ok) {
        setErrorMessage(message || `API Error (${res.status})`);
        return;
      }

      if (data.success === false) {
        setErrorMessage(message || 'Already subscribed');
        return;
      }

      setSuccessMessage(message || 'Subscribed successfully');
      setEmail('');
    } catch {
      setErrorMessage('Unable to subscribe right now');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className='flex flex-col gap-3 sm:flex-row sm:flex-wrap' onSubmit={onSubmit}>
      <Input
        type='email'
        required
        placeholder='you@company.com'
        className='w-full bg-white sm:max-w-sm'
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <Button type='submit' disabled={loading}>
        {loading ? 'Subscribing...' : 'Subscribe'}
      </Button>
      {successMessage ? <p className='w-full text-sm text-green-700'>{successMessage}</p> : null}
      {errorMessage ? <p className='w-full text-sm text-destructive'>{errorMessage}</p> : null}
    </form>
  );
}
