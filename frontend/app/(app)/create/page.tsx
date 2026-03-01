'use client';

import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import { useEffect, useMemo, useState } from 'react';

export const dynamic = "force-dynamic";

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';

type Client = {
  id: string;
  name: string;
};

type LineItem = {
  description: string;
  quantity: number;
  price: number;
  gst_percent: number;
};

export default function CreateInvoicePage() {
  useAuthGuard();

  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().split('T')[0]);
  const [invoiceType, setInvoiceType] = useState<'sales' | 'purchase'>('sales');
  const [gstNumber, setGstNumber] = useState('');
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<LineItem[]>([
    { description: '', quantity: 1, price: 0, gst_percent: 18 }
  ]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiRequest<Client[]>('/clients')
      .then((data) => setClients(data))
      .catch(() => setClients([]));
  }, []);

  const totals = useMemo(() => {
    let subtotal = 0;
    let gst = 0;

    items.forEach((item) => {
      const base = item.quantity * item.price;
      subtotal += base;
      gst += base * (item.gst_percent / 100);
    });

    return {
      subtotal,
      gst,
      total: subtotal + gst
    };
  }, [items]);

  const updateItem = (index: number, key: keyof LineItem, value: string) => {
    setItems((prev) =>
      prev.map((item, i) => {
        if (i !== index) return item;
        if (key === 'description') return { ...item, description: value };
        return { ...item, [key]: Number(value) };
      })
    );
  };

  const addItem = () => {
    setItems((prev) => [...prev, { description: '', quantity: 1, price: 0, gst_percent: 18 }]);
  };

  const removeItem = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const exportPdf = async () => {
    const pdf = await PDFDocument.create();
    const page = pdf.addPage([595, 842]);
    const font = await pdf.embedFont(StandardFonts.Helvetica);

    let y = 800;

    page.drawText('ScanMyBill.in Invoice Preview', {
      x: 40,
      y,
      size: 20,
      font,
      color: rgb(0.2, 0.2, 0.2)
    });

    y -= 40;
    page.drawText(`Invoice Date: ${invoiceDate}`, { x: 40, y, size: 12, font });
    y -= 20;
    page.drawText(`Invoice Type: ${invoiceType}`, { x: 40, y, size: 12, font });
    y -= 20;
    page.drawText(`GST Number: ${gstNumber || 'N/A'}`, { x: 40, y, size: 12, font });
    y -= 30;

    items.forEach((item, index) => {
      const lineTotal = item.quantity * item.price * (1 + item.gst_percent / 100);
      page.drawText(
        `${index + 1}. ${item.description || 'Item'} | Qty ${item.quantity} | Price ${item.price} | GST ${
          item.gst_percent
        }% | Total ${lineTotal.toFixed(2)}`,
        { x: 40, y, size: 11, font }
      );
      y -= 18;
    });

    y -= 20;
    page.drawText(`Subtotal: Rs ${totals.subtotal.toFixed(2)}`, { x: 40, y, size: 12, font });
    y -= 18;
    page.drawText(`GST: Rs ${totals.gst.toFixed(2)}`, { x: 40, y, size: 12, font });
    y -= 18;
    page.drawText(`Total: Rs ${totals.total.toFixed(2)}`, { x: 40, y, size: 14, font });

    const bytes = await pdf.save();
    const arrayBuffer = bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength
    ) as ArrayBuffer;
    const blob = new Blob([arrayBuffer], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${invoiceNumber || 'invoice-preview'}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const uploadInvoice = async () => {
    if (!items.length || items.some((item) => !item.description)) {
      alert('Please complete all item descriptions before upload.');
      return;
    }

    setSaving(true);
    try {
      await apiRequest('/invoices/create', {
        method: 'POST',
        body: {
          client_id: clientId || null,
          invoice_number: invoiceNumber || null,
          invoice_date: invoiceDate,
          gst_number: gstNumber || null,
          type: invoiceType,
          notes: notes || null,
          items
        }
      });
      alert('Invoice uploaded successfully.');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className='space-y-5'>
      <div>
        <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Create Invoice</h2>
        <p className='text-sm text-muted-foreground'>Build invoices, export to PDF, and save to database.</p>
      </div>

      <Card className='bg-white/85'>
        <CardHeader>
          <CardTitle>Invoice Builder</CardTitle>
        </CardHeader>
        <CardContent className='space-y-5'>
          <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
            <div className='space-y-1'>
              <Label>Client</Label>
              <Select value={clientId} onChange={(event) => setClientId(event.target.value)}>
                <option value=''>Select client</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className='space-y-1'>
              <Label>Invoice Number</Label>
              <Input value={invoiceNumber} onChange={(event) => setInvoiceNumber(event.target.value)} />
            </div>
            <div className='space-y-1'>
              <Label>Invoice Date</Label>
              <Input type='date' value={invoiceDate} onChange={(event) => setInvoiceDate(event.target.value)} />
            </div>
            <div className='space-y-1'>
              <Label>Type</Label>
              <Select
                value={invoiceType}
                onChange={(event) => setInvoiceType(event.target.value as 'sales' | 'purchase')}
              >
                <option value='sales'>Sales</option>
                <option value='purchase'>Purchase</option>
              </Select>
            </div>
            <div className='space-y-1'>
              <Label>GST Number</Label>
              <Input value={gstNumber} onChange={(event) => setGstNumber(event.target.value)} />
            </div>
          </div>

          <div className='space-y-3'>
            <div className='flex items-center justify-between'>
              <h3 className='font-semibold'>Items</h3>
              <Button variant='outline' onClick={addItem}>
                + Add Item
              </Button>
            </div>

            <div className='space-y-2'>
              {items.map((item, index) => (
                <div key={index} className='grid gap-2 rounded-md border border-border bg-background p-3 md:grid-cols-12'>
                  <Input
                    className='md:col-span-4'
                    placeholder='Description'
                    value={item.description}
                    onChange={(event) => updateItem(index, 'description', event.target.value)}
                  />
                  <Input
                    className='md:col-span-2'
                    type='number'
                    min={1}
                    value={item.quantity}
                    onChange={(event) => updateItem(index, 'quantity', event.target.value)}
                  />
                  <Input
                    className='md:col-span-2'
                    type='number'
                    min={0}
                    value={item.price}
                    onChange={(event) => updateItem(index, 'price', event.target.value)}
                  />
                  <Input
                    className='md:col-span-2'
                    type='number'
                    min={0}
                    max={100}
                    value={item.gst_percent}
                    onChange={(event) => updateItem(index, 'gst_percent', event.target.value)}
                  />
                  <Button
                    variant='destructive'
                    className='md:col-span-2'
                    onClick={() => removeItem(index)}
                    disabled={items.length === 1}
                  >
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          </div>

          <div className='grid gap-4 rounded-md border border-border bg-muted/20 p-4 md:grid-cols-3'>
            <p>Subtotal: Rs {totals.subtotal.toFixed(2)}</p>
            <p>GST: Rs {totals.gst.toFixed(2)}</p>
            <p className='font-semibold'>Total: Rs {totals.total.toFixed(2)}</p>
          </div>

          <div className='space-y-1'>
            <Label>Notes</Label>
            <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>

          <div className='flex flex-col gap-3 sm:flex-row'>
            <Button onClick={exportPdf} variant='outline'>
              Export (PDF)
            </Button>
            <Button onClick={uploadInvoice} disabled={saving}>
              {saving ? 'Uploading...' : 'Upload (Save in DB)'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
