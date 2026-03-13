'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { GoogleLogin } from '@react-oauth/google';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiRequest } from '@/lib/api';
import { setAuthSession } from '@/lib/auth';

const PERSONAL_DETAILS_SIGNUP_PROMPT_KEY = 'scanmybill_personal_details_signup_prompt';

type TokenResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    role: 'admin' | 'user';
    subscription_plan: 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';
    subscription_status: 'ACTIVE' | 'CANCELLED' | 'EXPIRED';
  };
};

export default function SignUpPage() {
  const router = useRouter();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const data = await apiRequest<TokenResponse>('/auth/create-account', {
        method: 'POST',
        auth: false,
        body: { full_name: fullName, email, password }
      });
      if (typeof window !== 'undefined') {
        localStorage.setItem(PERSONAL_DETAILS_SIGNUP_PROMPT_KEY, '1');
      }
      setAuthSession(data.access_token, data.user);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign up');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className='relative border-teal-200 bg-card/90 dark:border-slate-700'>
      <Button asChild type='button' variant='ghost' size='icon' className='absolute right-3 top-3 h-8 w-8' aria-label='Close and go to home'>
        <Link href='/'>
          <X className='h-4 w-4' />
        </Link>
      </Button>
      <CardHeader>
        <CardTitle className='font-[var(--font-space)] text-2xl'>Create Account</CardTitle>
        <CardDescription>Start managing invoices in minutes.</CardDescription>
      </CardHeader>
      <CardContent className='space-y-5'>
        <form className='space-y-4' onSubmit={onSubmit}>
          <div className='space-y-2'>
            <Label htmlFor='name'>Full Name</Label>
            <Input
              id='name'
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder='Your name'
              required
            />
          </div>
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
            <Label htmlFor='password'>Password</Label>
            <Input
              id='password'
              type='password'
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder='Minimum 8 characters'
              minLength={8}
              required
            />
          </div>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          <Button className='w-full' type='submit' disabled={loading}>
            {loading ? 'Creating Account...' : 'Create Account'}
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
                    if (typeof window !== 'undefined') {
                      localStorage.setItem(PERSONAL_DETAILS_SIGNUP_PROMPT_KEY, '1');
                    }
                    setAuthSession(data.access_token, data.user);
                    router.push('/dashboard');
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
          Already have an account?{' '}
          <Link href='/signin' className='font-medium text-primary'>
            Log in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}



