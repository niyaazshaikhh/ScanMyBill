"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Plus } from "lucide-react";

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
import { notifyApp } from "@/lib/app-notification";
import { isoMonthIndex, isoYear } from "@/lib/date-format";
import {
  appendDashboardDebugRecord,
  clearDashboardDebugResponses,
  DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY,
  DEBUG_MODE_STORAGE_KEY,
  DEBUG_MODE_CHANGED_EVENT,
  getDebugModeEnabled,
  readDashboardDebugResponses,
  type DashboardDebugConsoleRecord,
} from "@/lib/debugging";
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

type BillUploadApiResponse = Record<string, unknown>;
type PersonalDetailsPeriodResponse = {
  gst_filing_period: string | null;
};

const periodOptions = ["monthly", "quarterly", "semi-annually", "annually"];

function getFinancialYearStart(dateString: string) {
  const monthIndex = isoMonthIndex(dateString);
  const year = isoYear(dateString);
  return monthIndex >= 3 ? year : year - 1;
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
  const [debugModeEnabled, setDebugModeEnabled] = useState(false);
  const [debugConsoleEntries, setDebugConsoleEntries] = useState<DashboardDebugConsoleRecord[]>([]);
  const mainUploadInputRef = useRef<HTMLInputElement | null>(null);
  const quickUploadInputRef = useRef<HTMLInputElement | null>(null);

  const appendDebugEntry = useCallback(
    (entry: {
      level?: "info" | "success" | "warning" | "error";
      source?: string;
      title: string;
      message: string;
      file_name?: string;
      details?: unknown;
    }) => {
      const next = appendDashboardDebugRecord(entry);
      setDebugConsoleEntries(next);
    },
    [],
  );

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
    } catch (err) {
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
      appendDebugEntry({
        level: "warning",
        source: "dashboard",
        title: "Invoice year options fallback applied",
        message: err instanceof Error ? err.message : "Failed to fetch invoice list for year filter",
        details: err instanceof Error ? { name: err.name, stack: err.stack } : { error: String(err) },
      });
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
      const message = err instanceof Error ? err.message : "Failed to load dashboard";
      setError(message);
      appendDebugEntry({
        level: "error",
        source: "dashboard",
        title: "Dashboard summary load failed",
        message,
        details: err instanceof Error ? { name: err.name, stack: err.stack } : { error: String(err) },
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadYearOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let active = true;
    apiRequest<PersonalDetailsPeriodResponse>("/users/personal-details")
      .then((details) => {
        if (!active) return;
        const preferred = (details.gst_filing_period || "").trim().toLowerCase();
        if (preferred !== "monthly" && preferred !== "quarterly") return;
        setPeriod((current) => (current === "monthly" ? preferred : current));
      })
      .catch(() => {
        // Keep existing default period if personal details are unavailable.
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!year) return;
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, year]);

  useEffect(() => {
    setDebugModeEnabled(getDebugModeEnabled());
    setDebugConsoleEntries(readDashboardDebugResponses());

    const onDebugModeChange = (event: Event) => {
      const customEvent = event as CustomEvent<boolean>;
      if (typeof customEvent.detail === "boolean") {
        setDebugModeEnabled(customEvent.detail);
        return;
      }
      setDebugModeEnabled(getDebugModeEnabled());
    };

    const onStorage = (event: StorageEvent) => {
      if (!event.key) return;
      if (event.key === DEBUG_MODE_STORAGE_KEY) {
        setDebugModeEnabled(getDebugModeEnabled());
      }
      if (event.key === DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY) {
        setDebugConsoleEntries(readDashboardDebugResponses());
      }
    };

    window.addEventListener(DEBUG_MODE_CHANGED_EVENT, onDebugModeChange as EventListener);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(DEBUG_MODE_CHANGED_EVENT, onDebugModeChange as EventListener);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    const onWindowError = (event: ErrorEvent) => {
      appendDebugEntry({
        level: "error",
        source: "runtime",
        title: "Unhandled runtime error",
        message: event.message || "Unknown runtime error",
        details: {
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
          stack: event.error instanceof Error ? event.error.stack : null,
        },
      });
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const message = reason instanceof Error ? reason.message : String(reason);
      appendDebugEntry({
        level: "error",
        source: "runtime",
        title: "Unhandled promise rejection",
        message,
        details: reason instanceof Error ? { name: reason.name, stack: reason.stack } : { reason },
      });
    };

    window.addEventListener("error", onWindowError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onWindowError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, [appendDebugEntry]);

  const onClearDebugConsole = () => {
    clearDashboardDebugResponses();
    setDebugConsoleEntries([]);
  };

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

  const uploadFile = async (selectedFile: File) => {
    setUploading(true);
    setUploadMessage(null);
    appendDebugEntry({
      level: "info",
      source: "upload",
      title: "Bill upload started",
      message: `Uploading ${selectedFile.name}`,
      file_name: selectedFile.name,
      details: {
        size_bytes: selectedFile.size,
        mime_type: selectedFile.type,
      },
    });

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("invoice_type", "sales");

      const response = await apiRequest<BillUploadApiResponse>("/bills/upload", {
        method: "POST",
        body: formData,
        isFormData: true,
      });
      appendDebugEntry({
        level: "success",
        source: "upload",
        title: "Bill upload succeeded",
        message: "Upload pipeline completed successfully",
        file_name: selectedFile.name,
        details: response,
      });
      notifyApp({
        title: "Invoice uploaded successfully",
        message: "Invoice uploaded successfully",
        tone: "success",
      });
      setUploadMessage("Bill uploaded and processed successfully.");
      setFile(null);
      if (mainUploadInputRef.current) {
        mainUploadInputRef.current.value = "";
      }
      if (quickUploadInputRef.current) {
        quickUploadInputRef.current.value = "";
      }
      await loadYearOptions();
      await loadSummary();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      appendDebugEntry({
        level: "error",
        source: "upload",
        title: "Bill upload failed",
        message,
        file_name: selectedFile.name,
        details: err instanceof Error ? { name: err.name, stack: err.stack } : { error: String(err) },
      });
      setUploadMessage(message);
      notifyApp({
        title: "Invoice upload failed",
        message,
        tone: "error",
      });
    } finally {
      setUploading(false);
    }
  };

  const onUpload = async () => {
    if (!file) return;
    await uploadFile(file);
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
            Upload JPEG/PNG/PDF bills, run AI extraction, and auto-store
            structured records.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_130px]">
          <Input
            ref={mainUploadInputRef}
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

      {debugModeEnabled ? (
        <Card className="bg-white/85">
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>Debug Console</CardTitle>
                <CardDescription>
                  API payloads, upload traces, and runtime errors captured during dashboard activity.
                </CardDescription>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onClearDebugConsole}
                disabled={debugConsoleEntries.length === 0}
              >
                Clear all
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {debugConsoleEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No debug logs captured yet.
              </p>
            ) : (
              debugConsoleEntries.map((entry) => (
                <div key={entry.id} className="rounded-md border border-border bg-background/70 p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className={
                          entry.level === "error"
                            ? "border-red-200 bg-red-50 text-red-700"
                            : entry.level === "warning"
                              ? "border-amber-200 bg-amber-50 text-amber-700"
                              : entry.level === "success"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : "border-slate-200 bg-slate-50 text-slate-700"
                        }
                      >
                        {entry.level.toUpperCase()}
                      </Badge>
                      <span>{entry.source}</span>
                      {entry.file_name ? <span>File: {entry.file_name}</span> : null}
                    </div>
                    <span>{new Date(entry.created_at).toLocaleString("en-IN")}</span>
                  </div>
                  <p className="text-sm font-medium">{entry.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{entry.message}</p>
                  {entry.details !== undefined ? (
                    <pre className="mt-3 max-h-80 overflow-auto rounded bg-muted p-3 text-xs leading-relaxed">
                      {JSON.stringify(entry.details, null, 2)}
                    </pre>
                  ) : null}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ) : null}

      <input
        ref={quickUploadInputRef}
        type="file"
        accept=".jpeg,.jpg,.png,.pdf,.xls,.xlsx"
        className="hidden"
        onChange={(event) => {
          const selected = event.target.files?.[0] || null;
          if (!selected) return;
          void uploadFile(selected);
        }}
      />
      <Button
        type="button"
        onClick={() => {
          if (file) {
            void uploadFile(file);
            return;
          }
          quickUploadInputRef.current?.click();
        }}
        disabled={uploading}
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-orange-600 p-0 text-white shadow-lg hover:bg-orange-500 focus-visible:ring-orange-500"
        aria-label="Quick upload bill"
        title="Upload Bill"
      >
        {uploading ? (
          <Loader2 className="h-6 w-6 animate-spin" />
        ) : (
          <Plus className="h-7 w-7" />
        )}
      </Button>
    </div>
  );
}
