'use client';

import { useEffect, useMemo, useState } from 'react';

export const dynamic = "force-dynamic";

import { GstPieChart } from '@/components/charts/gst-pie';
import { SalesPurchaseLineChart } from '@/components/charts/sales-purchase-line';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';

type DashboardData = {
  total_sales: number;
  total_purchases: number;
  gst_collected: number;
  gst_paid: number;
  gst_payable: number;
  trend: { label: string; sales: number; purchases: number }[];
  gst_summary: { name: string; value: number }[];
};

const periodOptions = ['monthly', 'quarterly', 'semi-annually', 'annually'];

export default function DashboardPage() {
  useAuthGuard();

  const [period, setPeriod] = useState('monthly');
  const [summary, setSummary] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadType, setUploadType] = useState<'sales' | 'purchase'>('purchase');
  const [file, setFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const loadSummary = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<DashboardData>(`/dashboard/summary?period=${period}`);
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const cards = useMemo(
    () => [
      { title: 'Total Sales', value: summary?.total_sales ?? 0 },
      { title: 'Total Purchases', value: summary?.total_purchases ?? 0 },
      { title: 'GST Collected', value: summary?.gst_collected ?? 0 },
      { title: 'GST Paid', value: summary?.gst_paid ?? 0 },
      { title: 'GST Payable', value: summary?.gst_payable ?? 0 }
    ],
    [summary]
  );

  const onUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadMessage(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('invoice_type', uploadType);

      await apiRequest('/bills/upload', {
        method: 'POST',
        body: formData,
        isFormData: true
      });
      setUploadMessage('Bill uploaded and processed successfully.');
      setFile(null);
      await loadSummary();
    } catch (err) {
      setUploadMessage(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className='space-y-5'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Business Dashboard</h2>
          <p className='text-sm text-muted-foreground'>Sales, purchases, and GST health in one view.</p>
        </div>
        <div className='flex items-center gap-2'>
          <Label htmlFor='period' className='text-sm'>
            Filter
          </Label>
          <Select id='period' value={period} onChange={(event) => setPeriod(event.target.value)}>
            {periodOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <Card className='border-amber-300/80 bg-amber-50/70'>
        <CardHeader>
          <CardTitle>Bill Processing Flow</CardTitle>
          <CardDescription>
            Upload bill image/PDF, run OCR extraction, and auto-store structured records.
          </CardDescription>
        </CardHeader>
        <CardContent className='grid gap-3 md:grid-cols-[1fr_180px_130px]'>
          <Input
            type='file'
            accept='.pdf,image/*'
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          <Select value={uploadType} onChange={(event) => setUploadType(event.target.value as 'sales' | 'purchase')}>
            <option value='sales'>Sales</option>
            <option value='purchase'>Purchase</option>
          </Select>
          <Button onClick={onUpload} disabled={!file || uploading}>
            {uploading ? 'Uploading...' : 'Upload Bill'}
          </Button>
          {uploadMessage ? <p className='text-sm text-muted-foreground md:col-span-3'>{uploadMessage}</p> : null}
        </CardContent>
      </Card>

      {error ? <p className='text-sm text-destructive'>{error}</p> : null}
      {loading ? <p className='text-sm text-muted-foreground'>Loading dashboard...</p> : null}

      <div className='grid gap-4 sm:grid-cols-2 xl:grid-cols-5'>
        {cards.map((card) => (
          <Card key={card.title} className='bg-white/85'>
            <CardContent className='space-y-2 p-5'>
              <p className='text-xs font-semibold uppercase tracking-wide text-muted-foreground'>{card.title}</p>
              <p className='text-2xl font-semibold'>Rs {card.value.toLocaleString()}</p>
              {card.title === 'GST Payable' ? (
                <Badge variant={card.value >= 0 ? 'default' : 'success'}>
                  {card.value >= 0 ? 'Payable' : 'Credit'}
                </Badge>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className='grid gap-4 lg:grid-cols-2'>
        <Card className='bg-white/85'>
          <CardHeader>
            <CardTitle>Sales vs Purchases</CardTitle>
          </CardHeader>
          <CardContent>
            <SalesPurchaseLineChart data={summary?.trend ?? []} />
          </CardContent>
        </Card>

        <Card className='bg-white/85'>
          <CardHeader>
            <CardTitle>GST Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <GstPieChart data={summary?.gst_summary ?? []} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
