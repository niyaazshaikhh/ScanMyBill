'use client';

import { useEffect, useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { apiRequest } from '@/lib/api';

type Invoice = {
  id: string;
  client_name: string | null;
  invoice_date: string;
  gst_amount: number;
  total_amount: number;
  type: 'sales' | 'purchase';
};

type InvoiceListResponse = {
  invoices: Invoice[];
  count: number;
};

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function toBucket(dateString: string, period: string) {
  const date = new Date(dateString);
  if (period === 'monthly') return months[date.getMonth()];
  if (period === 'quarterly') return `Q${Math.floor(date.getMonth() / 3) + 1}`;
  if (period === 'semi-annually') return date.getMonth() < 6 ? 'H1' : 'H2';
  return String(date.getFullYear());
}

export default function InvoicesPage() {
  const [period, setPeriod] = useState('quarterly');
  const [invoiceType, setInvoiceType] = useState<'sales' | 'purchase'>('sales');
  const [selectedFolder, setSelectedFolder] = useState('Q1');
  const [data, setData] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadInvoices = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<InvoiceListResponse>(
        `/invoices?period=${period}&invoice_type=${invoiceType}`
      );
      setData(response.invoices);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load invoices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, invoiceType]);

  const folders = useMemo(() => {
    if (period === 'monthly') return months;
    if (period === 'quarterly') return ['Q1', 'Q2', 'Q3', 'Q4'];
    if (period === 'semi-annually') return ['H1', 'H2'];

    const years = Array.from(new Set(data.map((invoice) => new Date(invoice.invoice_date).getFullYear())))
      .sort((a, b) => a - b)
      .map(String);
    return years.length ? years : [String(new Date().getFullYear())];
  }, [data, period]);

  useEffect(() => {
    if (!folders.includes(selectedFolder)) {
      setSelectedFolder(folders[0]);
    }
  }, [folders, selectedFolder]);

  const folderInvoices = useMemo(
    () => data.filter((invoice) => toBucket(invoice.invoice_date, period) === selectedFolder),
    [data, period, selectedFolder]
  );

  const exportFolder = async () => {
    try {
      const blob = await apiRequest<Blob>(
        `/invoices/export-folder?period=${period}&bucket=${encodeURIComponent(selectedFolder)}&invoice_type=${invoiceType}`,
        { responseType: 'blob' }
      );

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${period}-${selectedFolder}-${invoiceType}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to export folder');
    }
  };

  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-end justify-between gap-3'>
        <div>
          <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Invoices</h2>
          <p className='text-sm text-muted-foreground'>Folder-style invoice explorer with consolidated export.</p>
        </div>
        <div className='grid gap-2 sm:grid-cols-3'>
          <div>
            <Label className='text-xs'>Period</Label>
            <Select value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value='monthly'>Monthly</option>
              <option value='quarterly'>Quarterly</option>
              <option value='semi-annually'>Semi-Annually</option>
              <option value='annually'>Annually</option>
            </Select>
          </div>
          <div>
            <Label className='text-xs'>Type</Label>
            <Select
              value={invoiceType}
              onChange={(event) => setInvoiceType(event.target.value as 'sales' | 'purchase')}
            >
              <option value='sales'>Sales</option>
              <option value='purchase'>Purchase</option>
            </Select>
          </div>
          <div className='flex items-end'>
            <Button onClick={exportFolder} className='w-full'>
              Export Folder PDF
            </Button>
          </div>
        </div>
      </div>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>Folders</CardTitle>
        </CardHeader>
        <CardContent className='grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6'>
          {folders.map((folder) => (
            <button
              key={folder}
              onClick={() => setSelectedFolder(folder)}
              className={`rounded-lg border p-3 text-left transition ${
                selectedFolder === folder
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-background hover:bg-muted'
              }`}
            >
              <p className='text-sm font-semibold'>{folder}</p>
              <p className='text-xs text-muted-foreground'>
                {data.filter((item) => toBucket(item.invoice_date, period) === folder).length} bills
              </p>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>
            {selectedFolder} <Badge variant='secondary'>{invoiceType}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {loading ? <p className='text-sm text-muted-foreground'>Loading invoices...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>GST</TableHead>
                  <TableHead>Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {folderInvoices.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className='text-center text-muted-foreground'>
                      No bills in this folder.
                    </TableCell>
                  </TableRow>
                ) : (
                  folderInvoices.map((invoice) => (
                    <TableRow key={invoice.id}>
                      <TableCell>{new Date(invoice.invoice_date).toLocaleDateString('en-IN')}</TableCell>
                      <TableCell>{invoice.client_name || 'Unlinked'}</TableCell>
                      <TableCell>Rs {invoice.gst_amount.toLocaleString()}</TableCell>
                      <TableCell>Rs {invoice.total_amount.toLocaleString()}</TableCell>
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