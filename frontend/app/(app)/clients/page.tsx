'use client';

import { useEffect, useState } from 'react';

export const dynamic = "force-dynamic";

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';

type ClientRow = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  gst_number: string | null;
  total_transactions: number;
  total_revenue: number;
};

type ClientsOverview = {
  total_clients: number;
  total_transactions: number;
  total_revenue: number;
  top_clients: { client_id: string; client_name: string; transactions: number; revenue: number }[];
};

export default function ClientsPage() {
  useAuthGuard();

  const [clients, setClients] = useState<ClientRow[]>([]);
  const [overview, setOverview] = useState<ClientsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [gst, setGst] = useState('');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [clientsData, analyticsData] = await Promise.all([
        apiRequest<ClientRow[]>('/clients'),
        apiRequest<ClientsOverview>('/clients/analytics')
      ]);
      setClients(clientsData);
      setOverview(analyticsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load clients');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const addClient = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await apiRequest('/clients', {
        method: 'POST',
        body: {
          name,
          email: email || null,
          phone: phone || null,
          gst_number: gst || null
        }
      });
      setName('');
      setEmail('');
      setPhone('');
      setGst('');
      setShowForm(false);
      await load();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Unable to add client');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className='space-y-5'>
      <div className='flex items-center justify-between'>
        <div>
          <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Clients</h2>
          <p className='text-sm text-muted-foreground'>Track client-level transactions and revenue.</p>
        </div>
        <Button onClick={() => setShowForm((prev) => !prev)}>+ Client</Button>
      </div>

      {showForm ? (
        <Card className='border-teal-200 bg-white/90'>
          <CardHeader>
            <CardTitle>Add Client</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={addClient} className='grid gap-3 md:grid-cols-2'>
              <div className='space-y-1'>
                <Label>Name</Label>
                <Input value={name} onChange={(event) => setName(event.target.value)} required />
              </div>
              <div className='space-y-1'>
                <Label>Email</Label>
                <Input
                  type='email'
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder='Optional'
                />
              </div>
              <div className='space-y-1'>
                <Label>Phone</Label>
                <Input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder='Optional' />
              </div>
              <div className='space-y-1'>
                <Label>GST Number</Label>
                <Input value={gst} onChange={(event) => setGst(event.target.value)} placeholder='Optional' />
              </div>
              <div className='md:col-span-2'>
                <Button type='submit' disabled={saving}>
                  {saving ? 'Saving...' : 'Save Client'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <div className='grid gap-4 sm:grid-cols-3'>
        <Card className='bg-white/85'>
          <CardContent className='p-5'>
            <p className='text-xs text-muted-foreground'>Total Clients</p>
            <p className='text-2xl font-semibold'>{overview?.total_clients ?? 0}</p>
          </CardContent>
        </Card>
        <Card className='bg-white/85'>
          <CardContent className='p-5'>
            <p className='text-xs text-muted-foreground'>Total Transactions</p>
            <p className='text-2xl font-semibold'>{overview?.total_transactions ?? 0}</p>
          </CardContent>
        </Card>
        <Card className='bg-white/85'>
          <CardContent className='p-5'>
            <p className='text-xs text-muted-foreground'>Total Revenue</p>
            <p className='text-2xl font-semibold'>Rs {(overview?.total_revenue ?? 0).toLocaleString()}</p>
          </CardContent>
        </Card>
      </div>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>Client List</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {loading ? <p className='text-sm text-muted-foreground'>Loading clients...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Client</TableHead>
                  <TableHead>Transactions</TableHead>
                  <TableHead>Total Revenue</TableHead>
                  <TableHead>GST Number</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clients.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className='text-center text-muted-foreground'>
                      No clients added yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  clients.map((client) => (
                    <TableRow key={client.id}>
                      <TableCell>
                        <p className='font-medium'>{client.name}</p>
                        <p className='text-xs text-muted-foreground'>{client.email || client.phone || 'No contact'}</p>
                      </TableCell>
                      <TableCell>{client.total_transactions}</TableCell>
                      <TableCell>Rs {client.total_revenue.toLocaleString()}</TableCell>
                      <TableCell>{client.gst_number || 'N/A'}</TableCell>
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
