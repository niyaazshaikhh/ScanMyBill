'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiRequest } from '@/lib/api';

type MessageResponse = {
  message: string;
};

const PASSWORD_POLICY_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,128}$/;
const PASSWORD_POLICY_MESSAGE =
  'Password must be 8-128 characters and include uppercase, lowercase, number, and special character.';

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    const tokenFromQuery = new URLSearchParams(window.location.search).get('token');
    if (tokenFromQuery) {
      setToken(tokenFromQuery);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const normalizedToken = token.trim();

    if (!normalizedToken) {
      setError('Reset link is invalid or expired. Please request a new reset email.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (!PASSWORD_POLICY_REGEX.test(newPassword)) {
      setError(PASSWORD_POLICY_MESSAGE);
      return;
    }

    setLoading(true);
    try {
      const data = await apiRequest<MessageResponse>('/auth/reset-password', {
        method: 'POST',
        auth: false,
        body: {
          token: normalizedToken,
          new_password: newPassword
        }
      });
      setSuccess(data.message);
      setNewPassword('');
      setConfirmPassword('');
      setToken('');
      router.push('/signin');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className='border-teal-200 bg-white/90'>
      <CardHeader>
        <CardTitle className='font-[var(--font-space)] text-2xl'>Reset Password</CardTitle>
        <CardDescription>Set a new password for your account.</CardDescription>
      </CardHeader>
      <CardContent className='space-y-5'>
        <form className='space-y-4' onSubmit={onSubmit}>
          <div className='space-y-2'>
            <Label htmlFor='new-password'>New Password</Label>
            <Input
              id='new-password'
              type='password'
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder='Minimum 8 characters'
              minLength={8}
              required
            />
            <p className='text-xs text-muted-foreground'>
              Use 8+ chars with uppercase, lowercase, number, and special character.
            </p>
          </div>
          <div className='space-y-2'>
            <Label htmlFor='confirm-password'>Confirm Password</Label>
            <Input
              id='confirm-password'
              type='password'
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder='Re-enter your new password'
              minLength={8}
              required
            />
          </div>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {success ? <p className='text-sm text-green-700'>{success}</p> : null}
          <Button className='w-full' type='submit' disabled={loading}>
            {loading ? 'Updating password...' : 'Update password'}
          </Button>
        </form>

        <p className='text-center text-sm text-muted-foreground'>
          Back to account access?{' '}
          <Link href='/signin' className='font-medium text-primary'>
            Log in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}
