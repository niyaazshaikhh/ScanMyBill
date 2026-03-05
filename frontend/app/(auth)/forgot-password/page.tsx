'use client';

import Link from 'next/link';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiRequest } from '@/lib/api';

type ForgotPasswordResponse = {
  message: string;
};

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const data = await apiRequest<ForgotPasswordResponse>('/auth/forgot-password', {
        method: 'POST',
        auth: false,
        body: { email }
      });

      setMessage(data.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to process request');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className='border-orange-200 bg-white/90'>
      <CardHeader>
        <CardTitle className='font-[var(--font-space)] text-2xl'>Forgot Password</CardTitle>
        <CardDescription>Enter your account email to generate a reset link.</CardDescription>
      </CardHeader>
      <CardContent className='space-y-5'>
        <form className='space-y-4' onSubmit={onSubmit}>
          <div className='space-y-2'>
            <Label htmlFor='email'>Email</Label>
            <Input
              id='email'
              type='email'
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder='you@company.com'
              required
            />
          </div>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {message ? <p className='text-sm text-green-700'>{message}</p> : null}
          <Button className='w-full' type='submit' disabled={loading}>
            {loading ? 'Generating reset link...' : 'Send reset link'}
          </Button>
        </form>

        <p className='text-center text-sm text-muted-foreground'>
          Remember your password?{' '}
          <Link href='/signin' className='font-medium text-primary'>
            Log in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
