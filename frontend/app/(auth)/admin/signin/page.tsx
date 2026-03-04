'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PopupWindow } from '@/components/ui/popup-window';
import { apiRequest } from '@/lib/api';
import { setAuthSession } from '@/lib/auth';

type AdminLoginResponse = {
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

function formatAdminSignInError(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'Unable to sign in. Please try again.';
  }

  const message = error.message.trim();
  if (!message) {
    return 'Unable to sign in. Please try again.';
  }

  const lowerMessage = message.toLowerCase();
  if (lowerMessage.includes('invalid credentials') || lowerMessage.includes('api error (401)')) {
    return 'Invalid Admin User ID or password.';
  }
  if (lowerMessage.includes('inactive')) {
    return 'Admin account is inactive. Please contact support.';
  }
  if (lowerMessage.includes('api error (422)') || lowerMessage.includes('admin_id') || lowerMessage.includes('password')) {
    return 'Please enter a valid Admin User ID and password.';
  }
  if (lowerMessage.includes('network error') || lowerMessage.includes('failed to fetch')) {
    return 'Unable to connect to the server. Check your network and backend API, then try again.';
  }
  if (lowerMessage.includes('session timed out')) {
    return 'Your session timed out. Please sign in again.';
  }

  return message;
}

export default function AdminSignInPage() {
  const router = useRouter();
  const [nextPath, setNextPath] = useState('/admin');
  const [adminId, setAdminId] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [popupMessage, setPopupMessage] = useState<string | null>(null);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setNextPath(query.get('next') || '/admin');
  }, []);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const normalizedAdminId = adminId.trim();
    if (!normalizedAdminId) {
      setPopupMessage('Admin User ID is required.');
      return;
    }
    if (!password.trim()) {
      setPopupMessage('Password is required.');
      return;
    }
    setLoading(true);
    setPopupMessage(null);

    try {
      const data = await apiRequest<AdminLoginResponse>('/auth/admin/login', {
        method: 'POST',
        auth: false,
        body: { admin_id: normalizedAdminId, password },
      });
      if (data.user.role !== 'admin') {
        throw new Error('Admin access denied');
      }
      setAuthSession(data.access_token, data.user);
      router.push(nextPath);
    } catch (err) {
      setPopupMessage(formatAdminSignInError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className='border-slate-300 bg-white/95'>
      <CardHeader>
        <CardTitle className='font-[var(--font-space)] text-2xl'>Admin Login</CardTitle>
        <CardDescription>Sign in to manage user accounts and access control.</CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <form className='space-y-4' onSubmit={onSubmit}>
          <div className='space-y-2'>
            <Label htmlFor='admin-id'>Admin User ID</Label>
            <Input
              id='admin-id'
              type='text'
              value={adminId}
              onChange={(event) => setAdminId(event.target.value)}
              placeholder='Enter admin user ID'
              required
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='admin-password'>Password</Label>
            <Input
              id='admin-password'
              type='password'
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder='Enter admin password'
              required
            />
          </div>
          <Button className='w-full' type='submit' disabled={loading}>
            {loading ? 'Signing in...' : 'Sign in as Admin'}
          </Button>
        </form>
        <p className='text-center text-sm text-muted-foreground'>
          Regular user access?{' '}
          <Link href='/signin' className='font-medium text-primary'>
            Go to user login
          </Link>
        </p>
      </CardContent>
      <PopupWindow
        open={Boolean(popupMessage)}
        title='Login Failed'
        message={popupMessage || ''}
        confirmLabel='OK'
        confirmVariant='destructive'
        onConfirm={() => setPopupMessage(null)}
      />
    </Card>
  );
}
