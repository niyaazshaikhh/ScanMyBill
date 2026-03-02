'use client';

import { useEffect, useMemo, useState } from 'react';
import { Eye } from 'lucide-react';

export const dynamic = "force-dynamic";

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import { formatAccountingAmount, formatAccountingInteger } from '@/lib/number-format';

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

function getFinancialYearStart(dateString: string) {
  const date = new Date(dateString);
  return date.getMonth() >= 3 ? date.getFullYear() : date.getFullYear() - 1;
}

function toFinancialYearLabel(startYear: number) {
  return `F.Y ${startYear}-${startYear + 1}`;
}

export default function InvoicesPage() {
  useAuthGuard();

  const [period, setPeriod] = useState('quarterly');
  const [year, setYear] = useState('');
  const [invoiceType, setInvoiceType] = useState<'sales' | 'purchase'>('sales');
  const [selectedFolder, setSelectedFolder] = useState('Q1');
  const [data, setData] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingInvoiceId, setDeletingInvoiceId] = useState<string | null>(null);
  const [previewingInvoiceId, setPreviewingInvoiceId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const yearOptions = useMemo(() => {
    const starts = Array.from(new Set(data.map((invoice) => getFinancialYearStart(invoice.invoice_date)))).sort(
      (a, b) => b - a
    );
    return starts.map((start) => ({ value: String(start), label: toFinancialYearLabel(start) }));
  }, [data]);

  const loadInvoices = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<InvoiceListResponse>(`/invoices?invoice_type=${invoiceType}`);
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
  }, [invoiceType]);

  useEffect(() => {
    if (yearOptions.length === 0) {
      setYear('');
      return;
    }
    if (!yearOptions.some((item) => item.value === year)) {
      setYear(yearOptions[0].value);
    }
  }, [yearOptions, year]);

  const yearFilteredInvoices = useMemo(() => {
    if (!year) return data;
    return data.filter((invoice) => getFinancialYearStart(invoice.invoice_date) === Number(year));
  }, [data, year]);

  const folders = useMemo(() => {
    if (period === 'monthly') return months;
    if (period === 'quarterly') return ['Q1', 'Q2', 'Q3', 'Q4'];
    if (period === 'semi-annually') return ['H1', 'H2'];

    const years = Array.from(new Set(yearFilteredInvoices.map((invoice) => new Date(invoice.invoice_date).getFullYear())))
      .sort((a, b) => a - b)
      .map(String);
    return years.length ? years : [];
  }, [yearFilteredInvoices, period]);

  useEffect(() => {
    if (folders.length === 0) {
      setSelectedFolder('');
      return;
    }
    if (!folders.includes(selectedFolder)) {
      setSelectedFolder(folders[0]);
    }
  }, [folders, selectedFolder]);

  const folderInvoices = useMemo(
    () => yearFilteredInvoices.filter((invoice) => toBucket(invoice.invoice_date, period) === selectedFolder),
    [yearFilteredInvoices, period, selectedFolder]
  );

  const exportFolder = async () => {
    if (!selectedFolder || !year) return;
    try {
      const blob = await apiRequest<Blob>(
        `/invoices/export-folder?period=${period}&financial_year_start=${year}&bucket=${encodeURIComponent(selectedFolder)}&invoice_type=${invoiceType}`,
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

  const deleteInvoice = async (invoiceId: string) => {
    const shouldDelete = window.confirm('Delete this bill? This action cannot be undone.');
    if (!shouldDelete) return;

    setDeletingInvoiceId(invoiceId);
    setActionMessage(null);

    try {
      await apiRequest(`/invoices/${invoiceId}`, { method: 'DELETE' });
      setActionMessage('Bill deleted successfully.');
      await loadInvoices();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Failed to delete bill');
    } finally {
      setDeletingInvoiceId(null);
    }
  };

  const previewInvoice = async (invoiceId: string) => {
    setPreviewingInvoiceId(invoiceId);
    setActionMessage(null);

    try {
      const blob = await apiRequest<Blob>(`/invoices/${invoiceId}/pdf`, { responseType: 'blob' });
      const previewUrl = URL.createObjectURL(blob);
      const popup = window.open(previewUrl, '_blank', 'noopener,noreferrer');
      if (!popup) {
        const link = document.createElement('a');
        link.href = previewUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(previewUrl), 60_000);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Failed to open bill PDF');
    } finally {
      setPreviewingInvoiceId(null);
    }
  };

  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-end justify-between gap-3'>
        <div>
          <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Invoices</h2>
          <p className='text-sm text-muted-foreground'>Folder-style invoice explorer with consolidated export.</p>
        </div>
        <div className='grid gap-2 sm:grid-cols-4'>
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
            <Label className='text-xs'>Year</Label>
            <Select value={year} onChange={(event) => setYear(event.target.value)}>
              {yearOptions.map((yearOption) => (
                <option key={yearOption.value} value={yearOption.value}>
                  {yearOption.label}
                </option>
              ))}
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
                {formatAccountingInteger(
                  yearFilteredInvoices.filter((item) => toBucket(item.invoice_date, period) === folder).length
                )}{' '}
                bills
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
          {actionMessage ? <p className='text-sm text-muted-foreground'>{actionMessage}</p> : null}
          {loading ? <p className='text-sm text-muted-foreground'>Loading invoices...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>GST</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead className='text-right'>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {folderInvoices.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className='text-center text-muted-foreground'>
                      No bills in this folder.
                    </TableCell>
                  </TableRow>
                ) : (
                  folderInvoices.map((invoice) => (
                    <TableRow key={invoice.id}>
                      <TableCell>{new Date(invoice.invoice_date).toLocaleDateString('en-IN')}</TableCell>
                      <TableCell>{invoice.client_name || 'Unlinked'}</TableCell>
                      <TableCell>Rs {formatAccountingAmount(invoice.gst_amount)}</TableCell>
                      <TableCell>Rs {formatAccountingAmount(invoice.total_amount)}</TableCell>
                      <TableCell className='text-right'>
                        <div className='flex justify-end gap-2'>
                          <Button
                            variant='outline'
                            size='icon'
                            onClick={() => previewInvoice(invoice.id)}
                            disabled={previewingInvoiceId === invoice.id}
                            title='View bill PDF'
                            aria-label='View bill PDF'
                          >
                            <Eye className='h-4 w-4' />
                          </Button>
                          <Button
                            variant='destructive'
                            size='sm'
                            onClick={() => deleteInvoice(invoice.id)}
                            disabled={deletingInvoiceId === invoice.id}
                          >
                            {deletingInvoiceId === invoice.id ? 'Deleting...' : 'Delete'}
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
    </div>
  );
}
