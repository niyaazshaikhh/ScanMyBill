'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { GoogleLogin } from '@react-oauth/google';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiRequest } from '@/lib/api';
import { setAuthSession } from '@/lib/auth';

type TokenResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    role: 'admin' | 'user';
  };
};

export default function SignInPage() {
  const router = useRouter();
  const [nextPath, setNextPath] = useState('/dashboard');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setNextPath(query.get('next') || '/dashboard');
  }, []);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const data = await apiRequest<TokenResponse>('/auth/login', {
        method: 'POST',
        auth: false,
        body: { email, password }
      });
      setAuthSession(data.access_token, data.user);
      router.push(nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to log in');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className='border-orange-200 bg-white/90'>
      <CardHeader>
        <CardTitle className='font-[var(--font-space)] text-2xl'>Log in</CardTitle>
        <CardDescription>Access your ScanMyBill.in workspace.</CardDescription>
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
          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <Label htmlFor='password'>Password</Label>
              <Link href='/forgot-password' className='text-xs font-medium text-primary'>
                Forgot password?
              </Link>
            </div>
            <Input
              id='password'
              type='password'
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder='Minimum 8 characters'
              required
            />
          </div>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          <Button className='w-full' type='submit' disabled={loading}>
            {loading ? 'Logging in...' : 'Log in'}
          </Button>
        </form>

        <div className='space-y-2'>
          <p className='text-center text-xs text-muted-foreground'>or continue with Google</p>
          {process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ? (
            <div className='flex justify-center'>
              <GoogleLogin
                text='continue_with'
                onSuccess={async (credentialResponse) => {
                  if (!credentialResponse.credential) return;
                  try {
                    const data = await apiRequest<TokenResponse>('/auth/google', {
                      method: 'POST',
                      auth: false,
                      body: { id_token: credentialResponse.credential }
                    });
                    setAuthSession(data.access_token, data.user);
                    router.push(nextPath);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Google login failed');
                  }
                }}
                onError={() => setError('Google login failed')}
              />
            </div>
          ) : (
            <p className='text-center text-xs text-muted-foreground'>
              Set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` to enable Google login.
            </p>
          )}
        </div>

        <p className='text-center text-sm text-muted-foreground'>
          New here?{' '}
          <Link href='/signup' className='font-medium text-primary'>
            Create an account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
