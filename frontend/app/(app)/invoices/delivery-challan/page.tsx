'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, Eye, Loader2, Plus, Trash2 } from 'lucide-react';

export const dynamic = "force-dynamic";

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { PopupWindow } from '@/components/ui/popup-window';
import { Select } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import { notifyApp } from '@/lib/app-notification';
import { formatIsoDateToDisplay, isoMonthIndex, isoYear } from '@/lib/date-format';
import { formatAccountingAmount, formatAccountingInteger } from '@/lib/number-format';
import { buildBillPdfFilename } from '@/lib/pdf-filename';

type DeliveryChallan = {
  id: string;
  client_name: string | null;
  challan_number: number;
  order_number: string;
  challan_date: string;
  subtotal: number;
};

type DeliveryChallanListResponse = {
  challans: DeliveryChallan[];
  count: number;
};

type SortBy = 'challan_number' | 'date' | 'order_number' | 'client_name' | 'amount';

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

export default function DeliveryChallanInvoicesPage() {
  useAuthGuard();
  const router = useRouter();
  const currentFinancialYearStart = getCurrentFinancialYearStart();

  const [period, setPeriod] = useState('quarterly');
  const [year, setYear] = useState(currentFinancialYearStart);
  const [selectedFolder, setSelectedFolder] = useState('Q1');
  const [sortBy, setSortBy] = useState<SortBy>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [data, setData] = useState<DeliveryChallan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewingId, setPreviewingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [uploadingBill, setUploadingBill] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [pendingDeleteChallan, setPendingDeleteChallan] = useState<{ id: string; challanNumber: string } | null>(null);
  const quickUploadInputRef = useRef<HTMLInputElement | null>(null);

  const yearOptions = useMemo(() => {
    const starts = new Set<number>(data.map((challan) => getFinancialYearStart(challan.challan_date)));
    starts.add(Number(currentFinancialYearStart));
    const sortedStarts = Array.from(starts).sort((a, b) => b - a);
    return sortedStarts.map((start) => ({ value: String(start), label: toFinancialYearLabel(start) }));
  }, [data, currentFinancialYearStart]);

  const loadChallans = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<DeliveryChallanListResponse>('/delivery-challans');
      setData(response.challans);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load delivery challans');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadChallans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!yearOptions.some((item) => item.value === year)) {
      setYear(currentFinancialYearStart);
    }
  }, [yearOptions, year, currentFinancialYearStart]);

  const yearFilteredChallans = useMemo(() => {
    if (year === ALL_FINANCIAL_YEARS) return data;
    return data.filter((challan) => getFinancialYearStart(challan.challan_date) === Number(year));
  }, [data, year]);

  const folders = useMemo(() => {
    if (period === 'monthly') return months;
    if (period === 'quarterly') return ['Q1', 'Q2', 'Q3', 'Q4'];
    if (period === 'semi-annually') return ['H1', 'H2'];

    const years = Array.from(new Set(yearFilteredChallans.map((challan) => isoYear(challan.challan_date))))
      .sort((a, b) => a - b)
      .map(String);
    return years.length ? years : [];
  }, [yearFilteredChallans, period]);

  useEffect(() => {
    if (folders.length === 0) {
      setSelectedFolder('');
      return;
    }
    if (!folders.includes(selectedFolder)) {
      setSelectedFolder(folders[0]);
    }
  }, [folders, selectedFolder]);

  const folderChallans = useMemo(
    () => yearFilteredChallans.filter((challan) => toBucket(challan.challan_date, period) === selectedFolder),
    [yearFilteredChallans, period, selectedFolder]
  );

  const sortedFolderChallans = useMemo(() => {
    const rows = [...folderChallans];
    rows.sort((left, right) => {
      let comparison = 0;
      if (sortBy === 'challan_number') {
        comparison = left.challan_number - right.challan_number;
      } else if (sortBy === 'date') {
        comparison = new Date(left.challan_date).getTime() - new Date(right.challan_date).getTime();
      } else if (sortBy === 'order_number') {
        comparison = left.order_number.localeCompare(right.order_number, undefined, {
          numeric: true,
          sensitivity: 'base',
        });
      } else if (sortBy === 'client_name') {
        comparison = (left.client_name || '').localeCompare(right.client_name || '', undefined, {
          sensitivity: 'base',
        });
      } else {
        comparison = left.subtotal - right.subtotal;
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });
    return rows;
  }, [folderChallans, sortBy, sortOrder]);

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

  const previewChallan = async (challanId: string) => {
    setPreviewingId(challanId);
    setActionMessage(null);
    try {
      const blob = await apiRequest<Blob>(`/delivery-challans/${challanId}/preview`, { responseType: 'blob' });
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
      setActionMessage(err instanceof Error ? err.message : 'Failed to open challan PDF');
    } finally {
      setPreviewingId(null);
    }
  };

  const downloadChallan = async (
    challanId: string,
    challanNumber: string,
    challanDate: string,
    clientName: string | null,
  ) => {
    setDownloadingId(challanId);
    setActionMessage(null);
    try {
      const blob = await apiRequest<Blob>(`/delivery-challans/${challanId}/pdf`, { responseType: 'blob' });
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = buildBillPdfFilename({
        billDateIso: challanDate,
        documentNumber: challanNumber,
        clientName,
      });
      link.click();
      URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Failed to download challan PDF');
    } finally {
      setDownloadingId(null);
    }
  };

  const deleteChallan = async (challanId: string, challanNumber: string) => {
    setDeletingId(challanId);
    setActionMessage(null);
    try {
      await apiRequest(`/delivery-challans/${challanId}`, { method: 'DELETE' });
      setData((previous) => previous.filter((challan) => challan.id !== challanId));
      setActionMessage(`Delivery challan ${challanNumber} deleted.`);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : 'Failed to delete delivery challan');
    } finally {
      setDeletingId(null);
    }
  };

  const confirmDeleteChallan = () => {
    if (!pendingDeleteChallan) return;
    const targetId = pendingDeleteChallan.id;
    const targetNumber = pendingDeleteChallan.challanNumber;
    setPendingDeleteChallan(null);
    void deleteChallan(targetId, targetNumber);
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
      await loadChallans();
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
            <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Delivery Challans</h2>
            <p className='text-sm text-muted-foreground'>View and download delivery challans by period folders.</p>
          </div>
          <div className='min-w-44 space-y-1'>
            <Label className='text-xs'>Challan Type</Label>
            <Select
              value='delivery'
              onChange={(event) => {
                if (event.target.value === 'gst') {
                  router.push('/invoices');
                }
              }}
            >
              <option value='gst'>GST Challan</option>
              <option value='delivery'>Delivery Challan</option>
            </Select>
          </div>
        </div>

        <div className='grid gap-2 sm:grid-cols-2'>
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
        </div>
      </div>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>Folders</CardTitle>
        </CardHeader>
        <CardContent className='grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6'>
          {folders.map((folder) => {
            const billCount = yearFilteredChallans.filter((item) => toBucket(item.challan_date, period) === folder).length;
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
                  {formatAccountingInteger(billCount)} challans
                </p>
              </button>
            );
          })}
        </CardContent>
      </Card>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>{selectedFolder}</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {actionMessage ? <p className='text-sm text-muted-foreground'>{actionMessage}</p> : null}
          {loading ? <p className='text-sm text-muted-foreground'>Loading challans...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <button
                      type='button'
                      onClick={() => onSortColumn('challan_number')}
                      className='inline-flex items-center gap-1 hover:text-foreground'
                    >
                      Challan Number
                      <span className='text-xs'>{sortTriangle('challan_number')}</span>
                    </button>
                  </TableHead>
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
                      onClick={() => onSortColumn('order_number')}
                      className='inline-flex items-center gap-1 hover:text-foreground'
                    >
                      Order Number
                      <span className='text-xs'>{sortTriangle('order_number')}</span>
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
                {sortedFolderChallans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className='text-center text-muted-foreground'>
                      No delivery challans in this folder.
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedFolderChallans.map((challan) => (
                    <TableRow key={challan.id}>
                      <TableCell>{challan.challan_number}</TableCell>
                      <TableCell>{formatIsoDateToDisplay(challan.challan_date)}</TableCell>
                      <TableCell>{challan.order_number}</TableCell>
                      <TableCell>{challan.client_name || 'Unlinked'}</TableCell>
                      <TableCell>Rs {formatAccountingAmount(challan.subtotal)}</TableCell>
                      <TableCell className='text-right'>
                        <div className='flex justify-end gap-2'>
                          <Button
                            variant='outline'
                            size='icon'
                            onClick={() => previewChallan(challan.id)}
                            disabled={
                              previewingId === challan.id || downloadingId === challan.id || deletingId === challan.id
                            }
                            title='View challan PDF'
                            aria-label='View challan PDF'
                          >
                            <Eye className='h-4 w-4' />
                          </Button>
                          <Button
                            variant='outline'
                            size='icon'
                            onClick={() =>
                              downloadChallan(
                                challan.id,
                                challan.order_number,
                                challan.challan_date,
                                challan.client_name,
                              )
                            }
                            disabled={
                              downloadingId === challan.id || previewingId === challan.id || deletingId === challan.id
                            }
                            title='Download challan PDF'
                            aria-label='Download challan PDF'
                          >
                            <Download className='h-4 w-4' />
                          </Button>
                          <Button
                            variant='outline'
                            size='icon'
                            onClick={() =>
                              setPendingDeleteChallan({
                                id: challan.id,
                                challanNumber: challan.order_number,
                              })
                            }
                            disabled={
                              deletingId === challan.id || previewingId === challan.id || downloadingId === challan.id
                            }
                            title='Delete challan'
                            aria-label='Delete challan'
                          >
                            <Trash2 className='h-4 w-4' />
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
      <PopupWindow
        open={Boolean(pendingDeleteChallan)}
        title='Delete Delivery Challan'
        message={
          pendingDeleteChallan
            ? `Delete delivery challan ${pendingDeleteChallan.challanNumber}? This action cannot be undone.`
            : ''
        }
        confirmLabel='Delete'
        cancelLabel='Cancel'
        confirmVariant='destructive'
        onCancel={() => setPendingDeleteChallan(null)}
        onConfirm={confirmDeleteChallan}
      />
    </div>
  );
}
