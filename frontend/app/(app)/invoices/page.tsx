'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, Eye, Loader2, Plus } from 'lucide-react';

export const dynamic = "force-dynamic";

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import { notifyApp } from '@/lib/app-notification';
import { formatIsoDateToDisplay, isoMonthIndex, isoYear } from '@/lib/date-format';
import { formatAccountingAmount, formatAccountingInteger } from '@/lib/number-format';
import { buildBillPdfFilename } from '@/lib/pdf-filename';

type SortBy = 'date' | 'invoice_number' | 'client_name' | 'amount';

type Invoice = {
  id: string;
  client_name: string | null;
  invoice_number: string;
  invoice_date: string;
  total_amount: number;
  type: 'sales' | 'purchase';
};

type InvoiceListResponse = {
  invoices: Invoice[];
  count: number;
};

const ALL_FINANCIAL_YEARS = 'all';
const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function toBucket(dateString: string, period: string) {
  const monthIndex = isoMonthIndex(dateString);
  const year = isoYear(dateString);
  if (period === 'monthly') return months[monthIndex];
  if (period === 'quarterly') return `Q${Math.floor(monthIndex / 3) + 1}`;
  if (period === 'semi-annually') return monthIndex < 6 ? 'H1' : 'H2';
  return String(year);
}

function getFinancialYearStart(dateString: string) {
  const monthIndex = isoMonthIndex(dateString);
  const year = isoYear(dateString);
  return monthIndex >= 3 ? year : year - 1;
}

function toFinancialYearLabel(startYear: number) {
  return `F.Y ${startYear}-${startYear + 1}`;
}

function getCurrentFinancialYearStart(): string {
  const now = new Date();
  const monthIndex = now.getMonth();
  const year = now.getFullYear();
  return String(monthIndex >= 3 ? year : year - 1);
}

export default function InvoicesPage() {
  useAuthGuard();
  const router = useRouter();
  const currentFinancialYearStart = getCurrentFinancialYearStart();

  const [period, setPeriod] = useState('quarterly');
  const [year, setYear] = useState(currentFinancialYearStart);
  const [invoiceType, setInvoiceType] = useState<'sales' | 'purchase'>('sales');
  const [sortBy, setSortBy] = useState<SortBy>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [selectedFolder, setSelectedFolder] = useState('Q1');
  const [data, setData] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingInvoiceId, setDeletingInvoiceId] = useState<string | null>(null);
  const [previewingInvoiceId, setPreviewingInvoiceId] = useState<string | null>(null);
  const [downloadingInvoiceId, setDownloadingInvoiceId] = useState<string | null>(null);
  const [uploadingBill, setUploadingBill] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const quickUploadInputRef = useRef<HTMLInputElement | null>(null);

  const yearOptions = useMemo(() => {
    const starts = new Set<number>(data.map((invoice) => getFinancialYearStart(invoice.invoice_date)));
    starts.add(Number(currentFinancialYearStart));
    const sortedStarts = Array.from(starts).sort((a, b) => b - a);
    return sortedStarts.map((start) => ({ value: String(start), label: toFinancialYearLabel(start) }));
  }, [data, currentFinancialYearStart]);

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
    if (!yearOptions.some((item) => item.value === year)) {
      setYear(currentFinancialYearStart);
    }
  }, [yearOptions, year, currentFinancialYearStart]);

  const yearFilteredInvoices = useMemo(() => {
    if (year === ALL_FINANCIAL_YEARS) return data;
    return data.filter((invoice) => getFinancialYearStart(invoice.invoice_date) === Number(year));
  }, [data, year]);

  const folders = useMemo(() => {
    if (period === 'monthly') return months;
    if (period === 'quarterly') return ['Q1', 'Q2', 'Q3', 'Q4'];
    if (period === 'semi-annually') return ['H1', 'H2'];

    const years = Array.from(new Set(yearFilteredInvoices.map((invoice) => isoYear(invoice.invoice_date))))
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

  const sortedFolderInvoices = useMemo(() => {
    const rows = [...folderInvoices];
    rows.sort((left, right) => {
      let comparison = 0;
      if (sortBy === 'date') {
        comparison = new Date(left.invoice_date).getTime() - new Date(right.invoice_date).getTime();
      } else if (sortBy === 'invoice_number') {
        comparison = left.invoice_number.localeCompare(right.invoice_number, undefined, {
          numeric: true,
          sensitivity: 'base',
        });
      } else if (sortBy === 'client_name') {
        comparison = (left.client_name || '').localeCompare(right.client_name || '', undefined, {
          sensitivity: 'base',
        });
      } else {
        comparison = left.total_amount - right.total_amount;
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });
    return rows;
  }, [folderInvoices, sortBy, sortOrder]);

  const sortTriangle = (column: SortBy) => {
    if (sortBy !== column) return '▵';
    return sortOrder === 'asc' ? '▴' : '▾';
  };

  const onSortColumn = (column: SortBy) => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortBy(column);
    setSortOrder('asc');
  };

  const exportFolder = async () => {
    if (!selectedFolder) return;
    const yearQuery = year === ALL_FINANCIAL_YEARS ? '' : `&financial_year_start=${year}`;
    try {
      const blob = await apiRequest<Blob>(
        `/invoices/export-folder?period=${period}&bucket=${encodeURIComponent(selectedFolder)}&invoice_type=${invoiceType}${yearQuery}`,
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
      const blob = await apiRequest<Blob>(`/invoices/${invoiceId}/preview`, { responseType: 'blob' });
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

  const downloadInvoice = async (
    invoiceId: string,
    invoiceNumber: string,
    invoiceDate: string,
    clientName: string | null,
  ) => {
    setDownloadingInvoiceId(invoiceId);
    setActionMessage(null);

    try {
      const blob = await apiRequest<Blob>(`/invoices/${invoiceId}/pdf`, { responseType: 'blob' });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = buildBillPdfFilename({
        billDateIso: invoiceDate,
        documentNumber: invoiceNumber,
        clientName,
      });
      link.click();
      URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Failed to download bill PDF');
    } finally {
      setDownloadingInvoiceId(null);
    }
  };

  const quickUploadBill = async (selectedFile: File) => {
    setUploadingBill(true);
    setActionMessage(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('invoice_type', 'sales');

      await apiRequest('/bills/upload', {
        method: 'POST',
        body: formData,
        isFormData: true,
      });
      notifyApp({
        title: 'Invoice uploaded successfully',
        message: 'Invoice uploaded successfully',
        tone: 'success',
      });
      await loadInvoices();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      notifyApp({
        title: 'Invoice upload failed',
        message,
        tone: 'error',
      });
      setActionMessage(message);
    } finally {
      setUploadingBill(false);
      if (quickUploadInputRef.current) {
        quickUploadInputRef.current.value = '';
      }
    }
  };

  return (
    <div className='space-y-5'>
      <div className='space-y-3'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div>
            <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Invoices</h2>
            <p className='text-sm text-muted-foreground'>Folder-style invoice explorer with consolidated export.</p>
          </div>
          <div className='min-w-44 space-y-1'>
            <Label className='text-xs'>Challan Type</Label>
            <Select
              value='gst'
              onChange={(event) => {
                if (event.target.value === 'delivery') {
                  router.push('/invoices/delivery-challan');
                }
              }}
            >
              <option value='gst'>GST Challan</option>
              <option value='delivery'>Delivery Challan</option>
            </Select>
          </div>
        </div>

        <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-4'>
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
              <option value={ALL_FINANCIAL_YEARS}>All Financial Years</option>
              {yearOptions.map((yearOption) => (
                <option key={yearOption.value} value={yearOption.value}>
                  {yearOption.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label className='text-xs'>Type</Label>
            <div className='mt-1 grid grid-cols-2 gap-2'>
              <Button
                type='button'
                size='sm'
                variant={invoiceType === 'sales' ? 'secondary' : 'outline'}
                onClick={() => setInvoiceType('sales')}
              >
                Sales
              </Button>
              <Button
                type='button'
                size='sm'
                variant={invoiceType === 'purchase' ? 'secondary' : 'outline'}
                onClick={() => setInvoiceType('purchase')}
              >
                Purchase
              </Button>
            </div>
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
          {folders.map((folder) => {
            const billCount = yearFilteredInvoices.filter((item) => toBucket(item.invoice_date, period) === folder).length;
            return (
              <button
                key={folder}
                onClick={() => setSelectedFolder(folder)}
                className={`relative rounded-lg border p-3 text-left transition ${
                  selectedFolder === folder
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-background hover:bg-muted'
                }`}
              >
                {billCount > 0 ? (
                  <span
                    className='absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-primary'
                    aria-hidden='true'
                  />
                ) : null}
                <p className='text-sm font-semibold'>{folder}</p>
                <p className='text-xs text-muted-foreground'>
                  {formatAccountingInteger(billCount)} bills
                </p>
              </button>
            );
          })}
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
                  <TableHead>
                    <button
                      type='button'
                      onClick={() => onSortColumn('date')}
                      className='inline-flex items-center gap-1 hover:text-foreground'
                    >
                      Date
                      <span className='text-xs'>{sortTriangle('date')}</span>
                    </button>
                  </TableHead>
                  <TableHead>
                    <button
                      type='button'
                      onClick={() => onSortColumn('invoice_number')}
                      className='inline-flex items-center gap-1 hover:text-foreground'
                    >
                      Invoice Number
                      <span className='text-xs'>{sortTriangle('invoice_number')}</span>
                    </button>
                  </TableHead>
                  <TableHead>
                    <button
                      type='button'
                      onClick={() => onSortColumn('client_name')}
                      className='inline-flex items-center gap-1 hover:text-foreground'
                    >
                      Client
                      <span className='text-xs'>{sortTriangle('client_name')}</span>
                    </button>
                  </TableHead>
                  <TableHead>
                    <button
                      type='button'
                      onClick={() => onSortColumn('amount')}
                      className='inline-flex items-center gap-1 hover:text-foreground'
                    >
                      Amount
                      <span className='text-xs'>{sortTriangle('amount')}</span>
                    </button>
                  </TableHead>
                  <TableHead className='text-right'>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedFolderInvoices.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className='text-center text-muted-foreground'>
                      No bills in this folder.
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedFolderInvoices.map((invoice) => (
                    <TableRow key={invoice.id}>
                      <TableCell>{formatIsoDateToDisplay(invoice.invoice_date)}</TableCell>
                      <TableCell>{invoice.invoice_number}</TableCell>
                      <TableCell>{invoice.client_name || 'Unlinked'}</TableCell>
                      <TableCell>Rs {formatAccountingAmount(invoice.total_amount)}</TableCell>
                      <TableCell className='text-right'>
                        <div className='flex justify-end gap-2'>
                          <Button
                            variant='outline'
                            size='icon'
                            onClick={() => previewInvoice(invoice.id)}
                            disabled={previewingInvoiceId === invoice.id || downloadingInvoiceId === invoice.id}
                            title='View bill PDF'
                            aria-label='View bill PDF'
                          >
                            <Eye className='h-4 w-4' />
                          </Button>
                          <Button
                            variant='outline'
                            size='icon'
                            onClick={() =>
                              downloadInvoice(
                                invoice.id,
                                invoice.invoice_number,
                                invoice.invoice_date,
                                invoice.client_name,
                              )
                            }
                            disabled={downloadingInvoiceId === invoice.id || previewingInvoiceId === invoice.id}
                            title='Download bill PDF'
                            aria-label='Download bill PDF'
                          >
                            <Download className='h-4 w-4' />
                          </Button>
                          <Button
                            variant='destructive'
                            size='sm'
                            onClick={() => deleteInvoice(invoice.id)}
                            disabled={
                              deletingInvoiceId === invoice.id
                              || previewingInvoiceId === invoice.id
                              || downloadingInvoiceId === invoice.id
                            }
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

      <input
        ref={quickUploadInputRef}
        type='file'
        accept='.jpeg,.jpg,.png,.pdf,.xls,.xlsx'
        className='hidden'
        onChange={(event) => {
          const selected = event.target.files?.[0] || null;
          if (!selected) return;
          void quickUploadBill(selected);
        }}
      />
      <Button
        type='button'
        onClick={() => quickUploadInputRef.current?.click()}
        disabled={uploadingBill}
        className='fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-orange-600 p-0 text-white shadow-lg hover:bg-orange-500 focus-visible:ring-orange-500'
        aria-label='Quick upload bill'
        title='Upload Bill'
      >
        {uploadingBill ? <Loader2 className='h-6 w-6 animate-spin' /> : <Plus className='h-7 w-7' />}
      </Button>
    </div>
  );
}
