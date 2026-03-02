'use client';

import { useEffect, useMemo, useState } from 'react';

export const dynamic = "force-dynamic";

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import { formatAccountingAmount, formatAccountingInteger } from '@/lib/number-format';

type ClientMaster = {
  id: string;
  name: string;
  email: string | null;
  gst_number: string | null;
};

type SalesInvoice = {
  id: string;
  client_id: string | null;
  invoice_date: string;
  total_amount: number;
  type: 'sales' | 'purchase';
};

type InvoiceListResponse = {
  invoices: SalesInvoice[];
  count: number;
};

type ClientAnalyticsRow = {
  id: string;
  name: string;
  gst_number: string | null;
  sales_bills: number;
  sales_revenue: number;
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

export default function ClientAnalyticsPage() {
  useAuthGuard();

  const [period, setPeriod] = useState('quarterly');
  const [year, setYear] = useState('');
  const [selectedFolder, setSelectedFolder] = useState('Q1');
  const [clients, setClients] = useState<ClientMaster[]>([]);
  const [salesInvoices, setSalesInvoices] = useState<SalesInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);

      try {
        const [clientData, invoiceData] = await Promise.all([
          apiRequest<ClientMaster[]>('/clients'),
          apiRequest<InvoiceListResponse>('/invoices?invoice_type=sales')
        ]);
        setClients(clientData);
        setSalesInvoices(invoiceData.invoices);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load client analytics');
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, []);

  const yearOptions = useMemo(() => {
    const starts = Array.from(new Set(salesInvoices.map((invoice) => getFinancialYearStart(invoice.invoice_date)))).sort(
      (a, b) => b - a
    );
    return starts.map((start) => ({ value: String(start), label: toFinancialYearLabel(start) }));
  }, [salesInvoices]);

  useEffect(() => {
    if (yearOptions.length === 0) {
      const now = new Date();
      const fyStart = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
      setYear(String(fyStart));
      return;
    }
    if (!yearOptions.some((item) => item.value === year)) {
      setYear(yearOptions[0].value);
    }
  }, [yearOptions, year]);

  const yearFilteredInvoices = useMemo(() => {
    if (!year) return salesInvoices;
    return salesInvoices.filter((invoice) => getFinancialYearStart(invoice.invoice_date) === Number(year));
  }, [salesInvoices, year]);

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

  const analyticsRows = useMemo<ClientAnalyticsRow[]>(() => {
    const totals = new Map<string, { bills: number; revenue: number }>();

    folderInvoices.forEach((invoice) => {
      if (!invoice.client_id) return;
      const existing = totals.get(invoice.client_id) || { bills: 0, revenue: 0 };
      existing.bills += 1;
      existing.revenue += invoice.total_amount;
      totals.set(invoice.client_id, existing);
    });

    return clients
      .map((client) => {
        const stats = totals.get(client.id) || { bills: 0, revenue: 0 };
        return {
          id: client.id,
          name: client.name,
          gst_number: client.gst_number,
          sales_bills: stats.bills,
          sales_revenue: stats.revenue
        };
      })
      .filter((row) => row.sales_bills > 0)
      .sort((a, b) => b.sales_revenue - a.sales_revenue);
  }, [clients, folderInvoices]);

  const summary = useMemo(() => {
    const activeClients = analyticsRows.length;
    const totalSalesBills = analyticsRows.reduce((sum, row) => sum + row.sales_bills, 0);
    const totalSalesRevenue = analyticsRows.reduce((sum, row) => sum + row.sales_revenue, 0);

    return {
      activeClients,
      totalSalesBills,
      totalSalesRevenue
    };
  }, [analyticsRows]);

  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-end justify-between gap-3'>
        <div>
          <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Client Analytics</h2>
          <p className='text-sm text-muted-foreground'>Sales analytics by client.</p>
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
                  yearFilteredInvoices.filter((invoice) => toBucket(invoice.invoice_date, period) === folder).length
                )}{' '}
                sales bills
              </p>
            </button>
          ))}
        </CardContent>
      </Card>

      <div className='grid gap-4 sm:grid-cols-3'>
        <Card className='bg-white/85'>
          <CardContent className='p-5'>
            <p className='text-xs text-muted-foreground'>Clients With Sales</p>
            <p className='text-2xl font-semibold'>{formatAccountingInteger(summary.activeClients)}</p>
          </CardContent>
        </Card>
        <Card className='bg-white/85'>
          <CardContent className='p-5'>
            <p className='text-xs text-muted-foreground'>Total Sales Bills</p>
            <p className='text-2xl font-semibold'>{formatAccountingInteger(summary.totalSalesBills)}</p>
          </CardContent>
        </Card>
        <Card className='bg-white/85'>
          <CardContent className='p-5'>
            <p className='text-xs text-muted-foreground'>Total Sales Revenue</p>
            <p className='text-2xl font-semibold'>Rs {formatAccountingAmount(summary.totalSalesRevenue)}</p>
          </CardContent>
        </Card>
      </div>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>
            {selectedFolder} Sales by Client
          </CardTitle>
        </CardHeader>
        <CardContent>
          {error ? <p className='text-sm text-destructive'>{error}</p> : null}
          {loading ? <p className='text-sm text-muted-foreground'>Loading client analytics...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Client</TableHead>
                  <TableHead>GST Number</TableHead>
                  <TableHead>Sales Bills</TableHead>
                  <TableHead className='text-right'>Sales Revenue</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {analyticsRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className='text-center text-muted-foreground'>
                      No sales analytics for this folder.
                    </TableCell>
                  </TableRow>
                ) : (
                  analyticsRows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className='font-medium'>{row.name}</TableCell>
                      <TableCell>{row.gst_number || 'N/A'}</TableCell>
                      <TableCell>{formatAccountingInteger(row.sales_bills)}</TableCell>
                      <TableCell className='text-right'>Rs {formatAccountingAmount(row.sales_revenue)}</TableCell>
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
