'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

export const dynamic = "force-dynamic";

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PopupWindow } from '@/components/ui/popup-window';
import { Select } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import {
  INDIAN_STATES_AND_UTS,
  getStateCodeByName,
  sanitizeAddressInput,
  sanitizeClientNameInput,
  sanitizeGstinInput,
  validateAddress,
  validateClientName,
  validateOptionalGstin,
  validateStateAndCodePair,
  validateStateCode,
  validateStateName
} from '@/lib/validation/business-details';

type ClientRow = {
  id: string;
  name: string;
  address: string | null;
  state_name: string | null;
  state_code: string | null;
  email: string | null;
  gst_number: string | null;
  total_transactions: number;
  total_revenue: number;
};

type PersonalDetailsResponse = {
  state_name: string | null;
  state_code: string | null;
};

export default function ClientsPage() {
  useAuthGuard();

  const router = useRouter();
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [stateName, setStateName] = useState('');
  const [stateCode, setStateCode] = useState('');
  const [email, setEmail] = useState('');
  const [gst, setGst] = useState('');
  const [editingClientId, setEditingClientId] = useState<string | null>(null);
  const [deletingClientId, setDeletingClientId] = useState<string | null>(null);
  const [pendingDeleteClient, setPendingDeleteClient] = useState<ClientRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [defaultStateName, setDefaultStateName] = useState('');
  const [defaultStateCode, setDefaultStateCode] = useState('');

  const resetForm = () => {
    setName('');
    setAddress('');
    setStateName(defaultStateName);
    setStateCode(defaultStateCode);
    setEmail('');
    setGst('');
    setEditingClientId(null);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const clientsData = await apiRequest<ClientRow[]>('/clients');
      setClients(clientsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load clients');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let active = true;

    apiRequest<PersonalDetailsResponse>('/users/personal-details')
      .then((details) => {
        if (!active) return;
        const configuredStateName = (details.state_name || '').trim();
        const configuredStateCode =
          getStateCodeByName(configuredStateName)
          || (details.state_code || '').trim();
        setDefaultStateName(configuredStateName);
        setDefaultStateCode(configuredStateCode);
      })
      .catch(() => {
        if (!active) return;
        setDefaultStateName('');
        setDefaultStateCode('');
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!showForm || editingClientId) return;
    if (!defaultStateName) return;
    setStateName((current) => current || defaultStateName);
    setStateCode((current) => current || defaultStateCode);
  }, [defaultStateCode, defaultStateName, editingClientId, showForm]);

  const mergeClientInState = (incomingClient: ClientRow) => {
    setClients((previousClients) => {
      const existingIndex = previousClients.findIndex(
        (existingClient) => existingClient.id === incomingClient.id,
      );
      if (existingIndex >= 0) {
        return previousClients.map((existingClient) =>
          existingClient.id === incomingClient.id ? incomingClient : existingClient,
        );
      }
      return [incomingClient, ...previousClients];
    });
  };

  const toggleCreateForm = () => {
    setActionMessage(null);
    setError(null);
    if (showForm) {
      setShowForm(false);
      resetForm();
      return;
    }
    resetForm();
    setShowForm(true);
  };

  const saveClient = async (event: React.FormEvent) => {
    event.preventDefault();
    setActionMessage(null);
    setError(null);

    const payload = {
      name: name.trim(),
      address: address.trim() || null,
      state_name: stateName.trim() || null,
      state_code: stateCode.trim() || null,
      email: email.trim() || null,
      gst_number: gst.trim().toUpperCase() || null
    };

    const nameError = validateClientName(payload.name);
    if (nameError) {
      setActionMessage(nameError);
      return;
    }

    if (payload.address) {
      const addressError = validateAddress(payload.address);
      if (addressError) {
        setActionMessage(addressError);
        return;
      }
    }

    if (payload.state_name || payload.state_code) {
      const stateNameError = validateStateName(payload.state_name || '');
      if (stateNameError) {
        setActionMessage(stateNameError);
        return;
      }

      const stateCodeError = validateStateCode(payload.state_code || '');
      if (stateCodeError) {
        setActionMessage(stateCodeError);
        return;
      }

      const statePairError = validateStateAndCodePair(payload.state_name || '', payload.state_code || '');
      if (statePairError) {
        setActionMessage(statePairError);
        return;
      }
    }

    if (payload.gst_number) {
      const gstValidationError = validateOptionalGstin(payload.gst_number);
      if (gstValidationError) {
        setActionMessage(gstValidationError);
        return;
      }
    }

    const targetEditingClientId = editingClientId;
    setShowForm(false);
    setSaving(true);
    try {
      let savedClient: ClientRow;
      if (targetEditingClientId) {
        savedClient = await apiRequest<ClientRow>(`/clients/${targetEditingClientId}`, {
          method: 'PUT',
          body: payload
        });
        mergeClientInState(savedClient);
        setActionMessage('Client updated successfully.');
      } else {
        savedClient = await apiRequest<ClientRow>('/clients', {
          method: 'POST',
          body: payload
        });
        mergeClientInState(savedClient);
        setActionMessage('Client added successfully.');
      }

      resetForm();
      setShowForm(false);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to save client');
    } finally {
      setSaving(false);
    }
  };

  const editClient = (client: ClientRow) => {
    setActionMessage(null);
    setError(null);
    setEditingClientId(client.id);
    setName(client.name);
    setAddress(client.address || '');
    setStateName(client.state_name || '');
    setStateCode(getStateCodeByName(client.state_name || '') || client.state_code || '');
    setEmail(client.email || '');
    setGst(client.gst_number || '');
    setShowForm(true);
  };

  const deleteClient = async (clientId: string) => {
    setActionMessage(null);
    setError(null);
    setDeletingClientId(clientId);

    try {
      await apiRequest(`/clients/${clientId}`, { method: 'DELETE' });
      setActionMessage('Client deleted successfully.');
      if (editingClientId === clientId) {
        resetForm();
        setShowForm(false);
      }
      await load();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Unable to delete client');
    } finally {
      setDeletingClientId(null);
    }
  };

  const confirmDeleteClient = () => {
    if (!pendingDeleteClient) return;
    const targetClientId = pendingDeleteClient.id;
    setPendingDeleteClient(null);
    void deleteClient(targetClientId);
  };

  const filteredClients = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return clients;

    return clients.filter((client) => {
      return (
        client.name.toLowerCase().includes(query)
        || (client.gst_number || '').toLowerCase().includes(query)
        || (client.email || '').toLowerCase().includes(query)
        || (client.address || '').toLowerCase().includes(query)
        || (client.state_name || '').toLowerCase().includes(query)
      );
    });
  }, [clients, searchQuery]);

  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Clients</h2>
          <p className='text-sm text-muted-foreground'>
            Master client list used in invoice generation.
          </p>
        </div>
        <Button onClick={toggleCreateForm}>{showForm ? 'Cancel' : '+ Client'}</Button>
      </div>

      {showForm ? (
        <Card className='border-teal-200 bg-card/90 dark:border-slate-700'>
          <CardHeader>
            <CardTitle>{editingClientId ? 'Edit Client' : 'Add Client'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={saveClient} className='grid gap-3 md:grid-cols-2'>
              <div className='space-y-1'>
                <Label>
                  Name <span className='text-destructive'>*</span>
                </Label>
                <Input
                  value={name}
                  onChange={(event) => setName(sanitizeClientNameInput(event.target.value))}
                  maxLength={30}
                  required
                />
              </div>
              <div className='space-y-1'>
                <Label>GST Number</Label>
                <Input
                  value={gst}
                  onChange={(event) => setGst(sanitizeGstinInput(event.target.value))}
                  maxLength={15}
                />
              </div>
              <div className='space-y-1 md:col-span-2'>
                <Label>Address</Label>
                <Textarea
                  value={address}
                  onChange={(event) => setAddress(sanitizeAddressInput(event.target.value))}
                  maxLength={115}
                />
                <p className='text-xs text-muted-foreground'>{address.length}/115</p>
              </div>
              <div className='space-y-1'>
                <Label>State Name</Label>
                <Select
                  value={stateName}
                  onChange={(event) => {
                    const selectedStateName = event.target.value;
                    const selectedStateCode = getStateCodeByName(selectedStateName) || '';
                    setStateName(selectedStateName);
                    setStateCode(selectedStateCode);
                  }}
                >
                  <option value=''>Select State / Union Territory</option>
                  {INDIAN_STATES_AND_UTS.map((stateOption) => (
                    <option key={stateOption.name} value={stateOption.name}>
                      {stateOption.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className='space-y-1'>
                <Label>State Code</Label>
                <Input value={stateCode} readOnly />
              </div>
              <div className='space-y-1 md:col-span-2'>
                <Label>Email</Label>
                <Input
                  type='email'
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder='Optional'
                />
              </div>
              <div className='md:col-span-2'>
                <div className='flex flex-wrap gap-2'>
                  <Button type='submit' disabled={saving}>
                    {saving ? 'Saving...' : editingClientId ? 'Update Client' : 'Save Client'}
                  </Button>
                  <Button
                    type='button'
                    variant='outline'
                    onClick={() => {
                      resetForm();
                      setShowForm(false);
                    }}
                  >
                    Close
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {actionMessage ? (
        <Card className='bg-card/85'>
          <CardContent className='p-4'>
            <p className='text-sm text-muted-foreground'>{actionMessage}</p>
          </CardContent>
        </Card>
      ) : null}

      <Card className='bg-card/85'>
        <CardHeader>
          <div className='flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between'>
            <CardTitle>Client Master List</CardTitle>
            <div className='w-full sm:max-w-sm'>
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder='Search by client, GST, email, address...'
                aria-label='Search clients'
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {loading ? <p className='text-sm text-muted-foreground'>Loading clients...</p> : null}
          {!loading && !error ? (
            <p className='mb-3 text-xs text-muted-foreground'>
              Showing {filteredClients.length} of {clients.length} clients
            </p>
          ) : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Client</TableHead>
                  <TableHead>GST Number</TableHead>
                  <TableHead className='text-right'>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredClients.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className='text-center text-muted-foreground'>
                      {clients.length === 0
                        ? 'No clients added yet.'
                        : 'No clients match your search.'}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredClients.map((client) => (
                    <TableRow key={client.id}>
                      <TableCell className='font-medium'>{client.name}</TableCell>
                      <TableCell>{client.gst_number || 'N/A'}</TableCell>
                      <TableCell className='text-right'>
                        <div className='flex flex-wrap justify-end gap-2'>
                          <Button
                            variant='secondary'
                            size='sm'
                            onClick={() => router.push(`/create?client_id=${encodeURIComponent(client.id)}`)}
                          >
                            Create Bill
                          </Button>
                          <Button variant='outline' size='sm' onClick={() => editClient(client)}>
                            Edit
                          </Button>
                          <Button
                            variant='destructive'
                            size='sm'
                            onClick={() => setPendingDeleteClient(client)}
                            disabled={deletingClientId === client.id}
                          >
                            {deletingClientId === client.id ? 'Deleting...' : 'Delete'}
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
      <PopupWindow
        open={Boolean(pendingDeleteClient)}
        title='Delete Client'
        message={
          pendingDeleteClient
            ? `Delete ${pendingDeleteClient.name}? This is allowed only when no invoices or delivery challans are linked to this client.`
            : ''
        }
        confirmLabel='Delete'
        cancelLabel='Cancel'
        confirmVariant='destructive'
        onCancel={() => setPendingDeleteClient(null)}
        onConfirm={confirmDeleteClient}
      />
    </div>
  );
}


