'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import { getAuthUser } from '@/lib/auth';
import { showAppErrorPopup, showAppSuccessPopup } from '@/lib/app-popup';

export const dynamic = 'force-dynamic';

type AdminUser = {
  id: string;
  full_name: string;
  email: string;
  role: 'admin' | 'user';
  is_active: boolean;
  subscription_plan: 'FREE' | 'STANDARD' | 'PRO' | 'BUSINESS';
  subscription_status: 'ACTIVE' | 'CANCELLED' | 'EXPIRED';
  created_at: string;
};

type AdminUsersResponse = {
  total_users: number;
  active_users: number;
  admin_users: number;
  users: AdminUser[];
};

export default function AdminPage() {
  useAuthGuard();

  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [activeUsers, setActiveUsers] = useState(0);
  const [adminUsers, setAdminUsers] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState('');

  const isAdminUser = getAuthUser()?.role === 'admin';

  useEffect(() => {
    if (!isAdminUser) {
      router.replace('/dashboard');
    }
  }, [isAdminUser, router]);

  const loadUsers = async (searchTerm = '') => {
    setLoading(true);
    try {
      const query = searchTerm.trim() ? `?search=${encodeURIComponent(searchTerm.trim())}` : '';
      const data = await apiRequest<AdminUsersResponse>(`/admin/users${query}`);
      setUsers(data.users || []);
      setTotalUsers(data.total_users || 0);
      setActiveUsers(data.active_users || 0);
      setAdminUsers(data.admin_users || 0);
    } catch {
      setUsers([]);
      setTotalUsers(0);
      setActiveUsers(0);
      setAdminUsers(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdminUser) return;
    const timeout = window.setTimeout(() => {
      void loadUsers(search);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [isAdminUser, search]);

  const resetSearch = () => {
    setSearch('');
  };

  const updateUser = async (userId: string, payload: { role?: 'admin' | 'user'; is_active?: boolean }) => {
    setSavingUserId(userId);
    try {
      await apiRequest(`/admin/users/${userId}`, {
        method: 'PATCH',
        body: payload,
      });
      await loadUsers(search);
      showAppSuccessPopup('User account updated successfully.', 'Admin');
    } catch {
      // API layer already shows popup errors.
    } finally {
      setSavingUserId(null);
    }
  };

  const submitPasswordReset = async () => {
    if (!resetTarget) return;
    if (newPassword.trim().length < 8) {
      showAppErrorPopup('Password must be at least 8 characters.', 'Validation Error');
      return;
    }

    setSavingUserId(resetTarget.id);
    try {
      await apiRequest(`/admin/users/${resetTarget.id}/reset-password`, {
        method: 'POST',
        body: { new_password: newPassword },
      });
      showAppSuccessPopup(`Password reset completed for ${resetTarget.email}.`, 'Admin');
      setResetTarget(null);
      setNewPassword('');
    } catch {
      // API layer already shows popup errors.
    } finally {
      setSavingUserId(null);
    }
  };

  return (
    <div className='space-y-5'>
      <div>
        <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Admin Console</h2>
        <p className='text-sm text-muted-foreground'>
          Manage user accounts, roles, and account access from one place.
        </p>
      </div>

      <div className='grid gap-2 md:grid-cols-3'>
        <Card className='bg-white/90'>
          <CardHeader className='pb-1 pt-4'>
            <CardTitle className='text-sm'>Total Users</CardTitle>
          </CardHeader>
          <CardContent className='pb-4'>
            <p className='text-xl font-semibold'>{totalUsers}</p>
          </CardContent>
        </Card>
        <Card className='bg-white/90'>
          <CardHeader className='pb-1 pt-4'>
            <CardTitle className='text-sm'>Active Users</CardTitle>
          </CardHeader>
          <CardContent className='pb-4'>
            <p className='text-xl font-semibold'>{activeUsers}</p>
          </CardContent>
        </Card>
        <Card className='bg-white/90'>
          <CardHeader className='pb-1 pt-4'>
            <CardTitle className='text-sm'>Admin Users</CardTitle>
          </CardHeader>
          <CardContent className='pb-4'>
            <p className='text-xl font-semibold'>{adminUsers}</p>
          </CardContent>
        </Card>
      </div>

      <Card className='bg-white/90'>
        <CardHeader className='space-y-3'>
          <CardTitle>User Management</CardTitle>
          <div className='flex flex-col gap-2 sm:flex-row'>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder='Search by name or email'
            />
            <Button type='button' variant='outline' onClick={resetSearch} disabled={loading || !search.trim()}>
              Reset
            </Button>
          </div>
        </CardHeader>
        <CardContent className='space-y-4'>
          {loading ? <p className='text-sm text-muted-foreground'>Loading users...</p> : null}

          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Subscription</TableHead>
                  <TableHead className='text-right'>Actions</TableHead>
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
                        <p className='font-medium'>{user.full_name}</p>
                        <p className='text-xs text-muted-foreground'>{user.email}</p>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.role === 'admin' ? 'success' : 'secondary'}>
                          {user.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.is_active ? 'default' : 'outline'}>
                          {user.is_active ? 'active' : 'inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <p className='text-sm font-medium'>{user.subscription_plan}</p>
                        <p className='text-xs text-muted-foreground'>{user.subscription_status}</p>
                      </TableCell>
                      <TableCell className='text-right'>
                        <div className='flex flex-wrap justify-end gap-2'>
                          <Button
                            size='sm'
                            variant='outline'
                            disabled={savingUserId === user.id}
                            onClick={() => void updateUser(user.id, { is_active: !user.is_active })}
                          >
                            {user.is_active ? 'Deactivate' : 'Activate'}
                          </Button>
                          <Button
                            size='sm'
                            variant='outline'
                            disabled={savingUserId === user.id}
                            onClick={() =>
                              void updateUser(user.id, { role: user.role === 'admin' ? 'user' : 'admin' })
                            }
                          >
                            {user.role === 'admin' ? 'Set User' : 'Set Admin'}
                          </Button>
                          <Button
                            size='sm'
                            disabled={savingUserId === user.id}
                            onClick={() => {
                              setResetTarget(user);
                              setNewPassword('');
                            }}
                          >
                            Reset Password
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>

      {resetTarget ? (
        <div className='fixed inset-0 z-[70] grid place-items-center bg-black/40 p-4'>
          <div className='w-full max-w-md rounded-lg border border-border bg-background p-5 shadow-xl'>
            <h3 className='text-base font-semibold text-foreground'>Reset User Password</h3>
            <p className='mt-1 text-sm text-muted-foreground'>
              Set a new password for {resetTarget.email}
            </p>
            <div className='mt-4 space-y-2'>
              <Label htmlFor='new-password'>New password</Label>
              <Input
                id='new-password'
                type='password'
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder='Minimum 8 characters'
              />
            </div>
            <div className='mt-5 flex justify-end gap-2'>
              <Button
                type='button'
                variant='outline'
                onClick={() => {
                  setResetTarget(null);
                  setNewPassword('');
                }}
                disabled={savingUserId === resetTarget.id}
              >
                Cancel
              </Button>
              <Button
                type='button'
                onClick={() => void submitPasswordReset()}
                disabled={savingUserId === resetTarget.id}
              >
                {savingUserId === resetTarget.id ? 'Saving...' : 'Reset Password'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
