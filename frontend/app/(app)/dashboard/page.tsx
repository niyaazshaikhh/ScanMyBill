"use client";

import { useEffect, useMemo, useState } from "react";

export const dynamic = "force-dynamic";

import { GstPieChart } from "@/components/charts/gst-pie";
import { SalesPurchaseLineChart } from "@/components/charts/sales-purchase-line";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";
import { formatAccountingAmount } from "@/lib/number-format";

type DashboardData = {
  total_sales: number;
  total_purchases: number;
  gst_collected: number;
  gst_paid: number;
  gst_payable: number;
  trend: { label: string; sales: number; purchases: number }[];
  gst_summary: { name: string; value: number }[];
};

type InvoiceYearItem = {
  invoice_date: string;
};

type InvoiceYearListResponse = {
  invoices: InvoiceYearItem[];
  count: number;
};

const periodOptions = ["monthly", "quarterly", "semi-annually", "annually"];

function getFinancialYearStart(dateString: string) {
  const date = new Date(dateString);
  return date.getMonth() >= 3 ? date.getFullYear() : date.getFullYear() - 1;
}

function toFinancialYearLabel(startYear: number) {
  return `F.Y ${startYear}-${startYear + 1}`;
}

function getCurrentFinancialYearStart() {
  const now = new Date();
  return now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
}

export default function DashboardPage() {
  useAuthGuard();

  const currentFinancialYearStart = getCurrentFinancialYearStart();
  const [period, setPeriod] = useState("monthly");
  const [year, setYear] = useState(String(currentFinancialYearStart));
  const [yearOptions, setYearOptions] = useState<{ value: string; label: string }[]>([
    {
      value: String(currentFinancialYearStart),
      label: toFinancialYearLabel(currentFinancialYearStart),
    },
  ]);
  const [summary, setSummary] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const loadYearOptions = async () => {
    try {
      const response = await apiRequest<InvoiceYearListResponse>("/invoices");
      const starts = Array.from(
        new Set(response.invoices.map((invoice) => getFinancialYearStart(invoice.invoice_date))),
      ).sort((a, b) => b - a);

      const normalized = starts.length > 0 ? starts : [currentFinancialYearStart];
      const options = normalized.map((start) => ({
        value: String(start),
        label: toFinancialYearLabel(start),
      }));
      setYearOptions(options);

      if (!options.some((option) => option.value === year)) {
        setYear(options[0].value);
      }
    } catch {
      // Keep fallback year option if invoices query fails.
      setYearOptions([
        {
          value: String(currentFinancialYearStart),
          label: toFinancialYearLabel(currentFinancialYearStart),
        },
      ]);
      if (!year) {
        setYear(String(currentFinancialYearStart));
      }
    }
  };

  const loadSummary = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<DashboardData>(
        `/dashboard/summary?period=${period}&financial_year_start=${year}`,
      );
      setSummary(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadYearOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!year) return;
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, year]);

  const cards = useMemo(
    () => [
      { title: "Total Sales", value: summary?.total_sales ?? 0 },
      { title: "Total Purchases", value: summary?.total_purchases ?? 0 },
      { title: "GST Collected", value: summary?.gst_collected ?? 0 },
      { title: "GST Paid", value: summary?.gst_paid ?? 0 },
      { title: "GST Payable", value: summary?.gst_payable ?? 0 },
    ],
    [summary],
  );

  const onUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadMessage(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("invoice_type", "sales");

      await apiRequest("/bills/upload", {
        method: "POST",
        body: formData,
        isFormData: true,
      });
      setUploadMessage("Bill uploaded and processed successfully.");
      setFile(null);
      await loadYearOptions();
      await loadSummary();
    } catch (err) {
      setUploadMessage(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-[var(--font-space)] text-2xl font-semibold">
            Business Dashboard
          </h2>
          <p className="text-sm text-muted-foreground">
            Sales, purchases, and GST health in one view.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <Label htmlFor="period" className="text-xs">
              Period
            </Label>
            <Select
              id="period"
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
            >
              {periodOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="year" className="text-xs">
              Year
            </Label>
            <Select
              id="year"
              value={year}
              onChange={(event) => setYear(event.target.value)}
            >
              {yearOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </div>

      <Card className="border-amber-300/80 bg-amber-50/70">
        <CardHeader>
          <CardTitle>Bill Processing Flow</CardTitle>
          <CardDescription>
            Upload JPEG/PNG/PDF bills, run OCR extraction, and auto-store
            structured records.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_130px]">
          <Input
            type="file"
            accept=".jpeg,.jpg,.png,.pdf,.xls,.xlsx"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          <Button onClick={onUpload} disabled={!file || uploading}>
            {uploading ? "Uploading..." : "Upload Bill"}
          </Button>
          {uploadMessage ? (
            <p className="text-sm text-muted-foreground md:col-span-2">
              {uploadMessage}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading dashboard...</p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {cards.map((card) => (
          <Card key={card.title} className="bg-white/85">
            <CardContent className="space-y-2 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {card.title}
              </p>
              <p className="text-2xl font-semibold">
                Rs {formatAccountingAmount(card.value)}
              </p>
              {card.title === "GST Payable" ? (
                <Badge variant={card.value >= 0 ? "default" : "success"}>
                  {card.value >= 0 ? "Payable" : "Credit"}
                </Badge>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="bg-white/85">
          <CardHeader>
            <CardTitle>Sales vs Purchases</CardTitle>
          </CardHeader>
          <CardContent>
            <SalesPurchaseLineChart data={summary?.trend ?? []} />
          </CardContent>
        </Card>

        <Card className="bg-white/85">
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
