'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiRequest } from '@/lib/api';

type NewsletterSubscribeResponse = {
  message: string;
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
      const response = await apiRequest<NewsletterSubscribeResponse>('/newsletter/subscribe', {
        method: 'POST',
        auth: false,
        body: { email }
      });
      setSuccessMessage(response.message || 'Subscribed successfully');
      setEmail('');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to subscribe right now');
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
