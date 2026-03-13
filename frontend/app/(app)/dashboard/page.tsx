"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
} from "react";
import { Loader2, Plus, Send, Sparkles, X } from "lucide-react";

export const dynamic = "force-dynamic";

import { GstPieChart } from "@/components/charts/gst-pie";
import { SalesPurchaseBarChart } from "@/components/charts/sales-purchase-line";
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
import { VerticalScrollNumber } from "@/components/ui/vertical-scroll-number";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";
import { notifyApp } from "@/lib/app-notification";
import { showAppErrorPopup, showAppInfoPopup } from "@/lib/app-popup";
import { getAuthUser } from "@/lib/auth";
import {
  getBillUploadState,
  startBillUpload,
  subscribeBillUpload,
  type BillUploadState,
} from "@/lib/bill-upload-manager";
import { isoMonthIndex, isoYear } from "@/lib/date-format";
import {
  appendDashboardDebugRecord,
  clearDashboardDebugResponses,
  DASHBOARD_DEBUG_RESPONSES_STORAGE_KEY,
  DASHBOARD_DEBUG_UPDATED_EVENT,
  DEBUG_MODE_STORAGE_KEY,
  DEBUG_MODE_CHANGED_EVENT,
  getDebugModeEnabled,
  readDashboardDebugResponses,
  type DashboardDebugConsoleRecord,
} from "@/lib/debugging";
import { formatAccountingAmount } from "@/lib/number-format";
import { cn } from "@/lib/utils";

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

type AIDebugAttempt = {
  provider?: string | null;
  model?: string | null;
  mode?: string | null;
  status?: string | null;
  error?: string | null;
};

type AIDebugTrace = {
  provider?: string | null;
  model?: string | null;
  result?: string | null;
  error?: string | null;
  details?: string | null;
  attempts?: AIDebugAttempt[];
};

type BillUploadApiResponse = {
  debug_trace?: AIDebugTrace | null;
  [key: string]: unknown;
};

type AIChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  createdAt: number;
};

type DashboardAssistantApiResponse = {
  answer: string;
  model: string;
};

type PersonalDetailsResponse = {
  company_name: string | null;
  gstin_number: string | null;
  address: string | null;
  state_name: string | null;
  state_code: string | null;
  gst_filing_period: string | null;
  email: string | null;
  bank_name: string | null;
  account_number: string | null;
  branch: string | null;
  ifsc_code: string | null;
};

type DashboardPeriod = "monthly" | "quarterly" | "semi-annually" | "annually";

const periodOptions: DashboardPeriod[] = ["monthly", "quarterly", "semi-annually", "annually"];
const SUPPORTED_UPLOAD_FORMAT_LABEL = "JPEG/PNG/PDF/DOCX/XLSX/CSV";
const SUPPORTED_UPLOAD_EXTENSIONS = new Set(["jpeg", "jpg", "png", "pdf", "docx", "xlsx", "csv"]);
const SUPPORTED_UPLOAD_MIME_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
  "application/csv",
  "application/vnd.ms-excel",
]);
const PERSONAL_DETAILS_REQUIRED_KEYS: Array<keyof PersonalDetailsResponse> = [
  "company_name",
  "gstin_number",
  "address",
  "state_name",
  "state_code",
  "gst_filing_period",
  "email",
  "bank_name",
  "account_number",
  "branch",
  "ifsc_code",
];

const AI_DEFAULT_PROMPTS = [
  "✨ Generate Business Summary",
  "How many invoices this month?",
] as const;

const AI_WELCOME_MESSAGE =
  "Hello! I'm ScanMyBill AI Assistant. Ask me about business performance, GST, or invoice trends.";

function getFinancialYearStart(dateString: string) {
  const monthIndex = isoMonthIndex(dateString);
  const year = isoYear(dateString);
  return monthIndex >= 3 ? year : year - 1;
}

function toFinancialYearLabel(startYear: number) {
  return `F.Y ${startYear}-${startYear + 1}`;
}

function extractFileExtension(fileName: string): string {
  const trimmed = fileName.trim();
  const dotIndex = trimmed.lastIndexOf(".");
  if (dotIndex < 0) return "";
  return trimmed.slice(dotIndex + 1).toLowerCase();
}

function isSupportedUploadFile(selectedFile: File): boolean {
  const extension = extractFileExtension(selectedFile.name);
  if (SUPPORTED_UPLOAD_EXTENSIONS.has(extension)) return true;

  const mimeType = (selectedFile.type || "").toLowerCase();
  return SUPPORTED_UPLOAD_MIME_TYPES.has(mimeType);
}

function getCurrentFinancialYearStart() {
  const now = new Date();
  return now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.trim();
  return cleaned.length > 0 ? cleaned : null;
}

function hasCompletedPersonalDetails(details: PersonalDetailsResponse): boolean {
  return PERSONAL_DETAILS_REQUIRED_KEYS.every((key) => {
    const value = details[key];
    return typeof value === "string" && value.trim().length > 0;
  });
}

function resolveUserDisplayName(): string {
  const user = getAuthUser();
  const fullName = (user?.full_name || "").trim();
  if (fullName) return fullName;
  const email = (user?.email || "").trim();
  if (email) {
    const prefix = email.split("@")[0]?.trim();
    if (prefix) return prefix;
  }
  return "User";
}

function summarizeProcessingSource(response: BillUploadApiResponse): {
  message: string;
  source_details: Record<string, unknown>;
} {
  const traceCandidate = response.debug_trace;
  const trace = isRecord(traceCandidate) ? traceCandidate : null;
  const provider = asString(trace?.provider);
  const model = asString(trace?.model);
  const result = asString(trace?.result);
  const traceError = asString(trace?.error);
  const traceDetails = asString(trace?.details);

  const attemptsRaw = Array.isArray(trace?.attempts) ? trace?.attempts : [];
  const attempts = attemptsRaw
    .filter((attempt) => isRecord(attempt))
    .map((attempt) => ({
      provider: asString(attempt.provider),
      model: asString(attempt.model),
      mode: asString(attempt.mode),
      status: asString(attempt.status),
      error: asString(attempt.error),
    }));

  const successfulAttempt = attempts.find((attempt) => attempt.status === "ok");
  const successfulMode = successfulAttempt?.mode || null;
  const serviceName = "ai_document_processor";

  const messageParts = ["Upload pipeline completed successfully"];
  if (provider || model || successfulMode) {
    const providerLabel = provider || "ai_provider";
    const modelLabel = model ? ` (${model})` : "";
    const modeLabel = successfulMode ? ` via ${successfulMode}` : "";
    messageParts.push(`Generator: ${providerLabel}${modelLabel}${modeLabel}`);
  } else {
    messageParts.push("Generator: api_service");
  }

  if (successfulMode === "ocr-only") {
    messageParts.push("OCR fallback used");
  }

  const sourceDetails: Record<string, unknown> = {
    service: serviceName,
    provider: provider,
    model: model,
    result: result,
    mode: successfulMode,
    ocr_fallback_used: successfulMode === "ocr-only",
  };
  if (traceError) {
    sourceDetails.error = traceError;
  }
  if (traceDetails) {
    sourceDetails.error_details = traceDetails;
  }
  if (attempts.length > 0) {
    sourceDetails.attempts = attempts;
  }

  return {
    message: messageParts.join(" | "),
    source_details: sourceDetails,
  };
}

export default function DashboardPage() {
  useAuthGuard();

  const currentFinancialYearStart = getCurrentFinancialYearStart();
  const [period, setPeriod] = useState<DashboardPeriod>("monthly");
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
  const [invoiceDates, setInvoiceDates] = useState<string[]>([]);

  const [uploadState, setUploadState] = useState<BillUploadState>(getBillUploadState());
  const uploading = uploadState.status === "uploading";
  const [file, setFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [debugModeEnabled, setDebugModeEnabled] = useState(false);
  const [debugConsoleEntries, setDebugConsoleEntries] = useState<DashboardDebugConsoleRecord[]>([]);
  const [dashboardUserName, setDashboardUserName] = useState("User");
  const [showPersonalDetailsBanner, setShowPersonalDetailsBanner] = useState(false);
  const [isUploadDropActive, setIsUploadDropActive] = useState(false);
  const [aiChatOpen, setAiChatOpen] = useState(false);
  const [aiChatThinking, setAiChatThinking] = useState(false);
  const [aiChatInput, setAiChatInput] = useState("");
  const [aiModelLabel, setAiModelLabel] = useState("OPENAI_MODEL");
  const [aiChatMessages, setAiChatMessages] = useState<AIChatMessage[]>([
    {
      id: "assistant-welcome",
      role: "assistant",
      content: AI_WELCOME_MESSAGE,
      createdAt: Date.now(),
    },
  ]);
  const mainUploadInputRef = useRef<HTMLInputElement | null>(null);
  const quickUploadInputRef = useRef<HTMLInputElement | null>(null);
  const aiChatEndRef = useRef<HTMLDivElement | null>(null);

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
      setInvoiceDates(response.invoices.map((invoice) => invoice.invoice_date));
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
      setInvoiceDates([]);
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
    setDashboardUserName(resolveUserDisplayName());
  }, []);

  useEffect(() => {
    let active = true;
    apiRequest<PersonalDetailsResponse>("/users/personal-details")
      .then((details) => {
        if (!active) return;
        setShowPersonalDetailsBanner(!hasCompletedPersonalDetails(details));
        const preferred = (details.gst_filing_period || "").trim().toLowerCase();
        if (preferred !== "monthly" && preferred !== "quarterly") return;
        setPeriod((current) => (current === "monthly" ? preferred : current));
      })
      .catch(() => {
        // Keep existing default period if personal details are unavailable.
        setShowPersonalDetailsBanner(false);
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

    const onDebugEntriesUpdated = (event: Event) => {
      const customEvent = event as CustomEvent<DashboardDebugConsoleRecord[]>;
      if (Array.isArray(customEvent.detail)) {
        setDebugConsoleEntries(customEvent.detail);
        return;
      }
      setDebugConsoleEntries(readDashboardDebugResponses());
    };

    window.addEventListener(DEBUG_MODE_CHANGED_EVENT, onDebugModeChange as EventListener);
    window.addEventListener("storage", onStorage);
    window.addEventListener(DASHBOARD_DEBUG_UPDATED_EVENT, onDebugEntriesUpdated as EventListener);
    return () => {
      window.removeEventListener(DEBUG_MODE_CHANGED_EVENT, onDebugModeChange as EventListener);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(DASHBOARD_DEBUG_UPDATED_EVENT, onDebugEntriesUpdated as EventListener);
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

  useEffect(() => {
    let previousState = getBillUploadState();
    return subscribeBillUpload((nextState) => {
      setUploadState(nextState);

      const completedUpload =
        previousState.status === "uploading" &&
        (nextState.status === "success" || nextState.status === "error");
      if (!completedUpload) {
        previousState = nextState;
        return;
      }

      if (nextState.status === "success") {
        const uploadResponse =
          isRecord(nextState.response) ? (nextState.response as BillUploadApiResponse) : {};
        const processingSource = summarizeProcessingSource(uploadResponse);
        appendDebugEntry({
          level: "success",
          source: "upload",
          title: "Bill upload succeeded",
          message: processingSource.message,
          file_name: nextState.fileName || undefined,
          details: {
            processing_source: processingSource.source_details,
            response: uploadResponse,
          },
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
        void loadYearOptions();
        void loadSummary();
      } else {
        const message = nextState.error || "Upload failed";
        appendDebugEntry({
          level: "error",
          source: "upload",
          title: "Bill upload failed",
          message,
          file_name: nextState.fileName || undefined,
          details: isRecord(nextState.response)
            ? nextState.response
            : { error: message },
        });
        setUploadMessage(message);
        notifyApp({
          title: "Invoice upload failed",
          message,
          tone: "error",
        });
      }

      previousState = nextState;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const resolveSupportedFile = useCallback(
    (selectedFile: File | null): File | null => {
      if (!selectedFile) return null;
      if (isSupportedUploadFile(selectedFile)) return selectedFile;

      const message = `This file format is unsupported. Please try with supported files: ${SUPPORTED_UPLOAD_FORMAT_LABEL}.`;
      showAppErrorPopup(message, "Unsupported File Format");
      appendDebugEntry({
        level: "warning",
        source: "upload",
        title: "Unsupported upload file blocked",
        message,
        file_name: selectedFile.name,
        details: {
          mime_type: selectedFile.type || null,
          size_bytes: selectedFile.size,
        },
      });
      return null;
    },
    [appendDebugEntry],
  );

  const onUploadZoneDragEnter = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!Array.from(event.dataTransfer.types || []).includes("Files")) return;
    event.preventDefault();
    setIsUploadDropActive(true);
  }, []);

  const onUploadZoneDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    if (!Array.from(event.dataTransfer.types || []).includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsUploadDropActive(true);
  }, []);

  const onUploadZoneDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setIsUploadDropActive(false);
  }, []);

  const uploadFile = useCallback(
    async (selectedFile: File) => {
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
        await startBillUpload(selectedFile, { invoiceType: "sales" });
      } catch {
        // Upload completion and errors are handled by the shared upload-state subscriber.
      }
    },
    [appendDebugEntry],
  );

  const onUpload = async () => {
    if (!file) return;
    await uploadFile(file);
  };

  const onUploadZoneDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      if (!Array.from(event.dataTransfer.types || []).includes("Files")) return;
      event.preventDefault();
      setIsUploadDropActive(false);

      if (uploading) {
        showAppInfoPopup("A bill upload is already in progress. Please wait for it to complete.", "Upload In Progress");
        return;
      }

      const droppedFile = resolveSupportedFile(event.dataTransfer.files?.[0] || null);
      if (!droppedFile) return;

      setFile(droppedFile);
      void uploadFile(droppedFile);
    },
    [resolveSupportedFile, uploadFile, uploading],
  );

  const buildFallbackAssistantResponse = useCallback(
    (prompt: string): string => {
      const normalized = prompt.trim().toLowerCase();
      const now = new Date();
      const monthLabel = now.toLocaleString("en-IN", { month: "long", year: "numeric" });

      if (
        normalized.includes("how many invoices this month")
        || (normalized.includes("invoice") && normalized.includes("month"))
      ) {
        const monthlyInvoiceCount = invoiceDates.filter((dateValue) => {
          const parsed = new Date(dateValue);
          if (Number.isNaN(parsed.getTime())) return false;
          return parsed.getMonth() === now.getMonth() && parsed.getFullYear() === now.getFullYear();
        }).length;

        return `For ${monthLabel}, you have ${monthlyInvoiceCount} invoice${
          monthlyInvoiceCount === 1 ? "" : "s"
        } recorded. Keep uploading daily bills to maintain an accurate month-end snapshot.`;
      }

      const totalSales = summary?.total_sales ?? 0;
      const totalPurchases = summary?.total_purchases ?? 0;
      const gstCollected = summary?.gst_collected ?? 0;
      const gstPaid = summary?.gst_paid ?? 0;
      const gstPayable = summary?.gst_payable ?? 0;
      const latestTrendPoint = (summary?.trend || [])[summary?.trend.length ? summary.trend.length - 1 : 0];

      const trendLine = latestTrendPoint
        ? `In ${latestTrendPoint.label}, sales are Rs ${formatAccountingAmount(
            latestTrendPoint.sales,
          )} and purchases are Rs ${formatAccountingAmount(latestTrendPoint.purchases)}.`
        : "Trend details are limited right now because recent transaction buckets are still sparse.";

      return `Business summary: Sales Rs ${formatAccountingAmount(totalSales)}, Purchases Rs ${formatAccountingAmount(
        totalPurchases,
      )}, GST Collected Rs ${formatAccountingAmount(gstCollected)}, GST Paid Rs ${formatAccountingAmount(
        gstPaid,
      )}, and GST Payable Rs ${formatAccountingAmount(gstPayable)}. ${trendLine}`;
    },
    [invoiceDates, summary],
  );

  const sendAIMessage = useCallback(
    async (rawPrompt: string) => {
      const prompt = rawPrompt.trim();
      if (!prompt || aiChatThinking) return;

      const userMessage: AIChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: prompt,
        createdAt: Date.now(),
      };
      const nextHistory = [...aiChatMessages, userMessage]
        .slice(-10)
        .map((item) => ({ role: item.role, content: item.content }));
      setAiChatMessages((previous) => [...previous, userMessage]);
      setAiChatInput("");
      setAiChatThinking(true);

      try {
        let assistantReply = "";
        try {
          const requestedYear = Number(year);
          const response = await apiRequest<DashboardAssistantApiResponse>("/dashboard/assistant", {
            method: "POST",
            body: {
              message: prompt,
              period,
              financial_year_start:
                Number.isInteger(requestedYear) && requestedYear >= 2000 ? requestedYear : null,
              history: nextHistory,
            },
          });
          assistantReply = (response.answer || "").trim();
          if (response.model?.trim()) {
            setAiModelLabel(response.model.trim());
          }
        } catch {
          // Fallback keeps chat responsive if AI service is temporarily unavailable.
          assistantReply = buildFallbackAssistantResponse(prompt);
        }

        if (!assistantReply) {
          assistantReply = buildFallbackAssistantResponse(prompt);
        }

        const assistantMessage: AIChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: assistantReply,
          createdAt: Date.now(),
        };
        setAiChatMessages((previous) => [...previous, assistantMessage]);
      } finally {
        setAiChatThinking(false);
      }
    },
    [aiChatMessages, aiChatThinking, buildFallbackAssistantResponse, period, year],
  );

  const onSubmitAIChat = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void sendAIMessage(aiChatInput);
  };

  const onResetAIChat = () => {
    setAiChatInput("");
    setAiChatThinking(false);
    setAiChatMessages([
      {
        id: `assistant-welcome-${Date.now()}`,
        role: "assistant",
        content: AI_WELCOME_MESSAGE,
        createdAt: Date.now(),
      },
    ]);
  };

  useEffect(() => {
    if (!aiChatOpen) return;
    aiChatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [aiChatMessages, aiChatOpen, aiChatThinking]);

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
              onChange={(event) => setPeriod(event.target.value as DashboardPeriod)}
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

      {showPersonalDetailsBanner ? (
        <p className="text-sm font-medium text-red-600 dark:text-red-300">
          ⚠️ {dashboardUserName} has not set up their Business Setup profile.
          Please{" "}
          <Link
            href="/settings/personal_details"
            className="font-semibold text-red-700 underline underline-offset-2 hover:text-red-800 dark:text-red-200 dark:hover:text-red-100"
          >
            click here
          </Link>{" "}
          to fill the details.
        </p>
      ) : null}

      <Card
        className={cn(
          "border-amber-300/80 bg-amber-50/70 transition-colors dark:border-amber-500/45 dark:bg-amber-500/15",
          isUploadDropActive && "border-primary/70 bg-primary/10 ring-2 ring-primary/40",
        )}
        onDragEnter={onUploadZoneDragEnter}
        onDragOver={onUploadZoneDragOver}
        onDragLeave={onUploadZoneDragLeave}
        onDrop={onUploadZoneDrop}
      >
        <CardHeader>
          <CardTitle>Bill Processing Flow</CardTitle>
          <CardDescription>
            Upload JPEG/PNG/PDF/DOCX/XLSX/CSV bills, run AI extraction, and
            auto-store structured records.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_130px]">
          <Input
            ref={mainUploadInputRef}
            type="file"
            accept=".jpeg,.jpg,.png,.pdf,.docx,.xlsx,.csv"
            onChange={(event) => {
              const selectedFile = resolveSupportedFile(event.target.files?.[0] || null);
              setFile(selectedFile);
              if (!selectedFile) {
                event.target.value = "";
              }
            }}
          />
          <Button onClick={onUpload} disabled={!file || uploading}>
            {uploading ? "Uploading..." : "Upload Bill"}
          </Button>
          <p
            className={cn(
              "text-xs md:col-span-2",
              isUploadDropActive ? "font-medium text-primary" : "text-muted-foreground",
            )}
          >
            {isUploadDropActive
              ? "Drop file to upload now"
              : `Drag and drop files here to upload bills. Supported: ${SUPPORTED_UPLOAD_FORMAT_LABEL}.`}
          </p>
          {uploading ? (
            <div className="space-y-2 md:col-span-2">
              <p className="truncate text-xs text-muted-foreground">
                {uploadState.fileName
                  ? `Uploading challan: ${uploadState.fileName}`
                  : "Uploading challan..."}
              </p>
              <div className="relative h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="upload-marquee-indicator absolute inset-y-0 left-0 w-1/3 rounded-full bg-orange-500"
                />
              </div>
            </div>
          ) : null}
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
          <Card key={card.title} className="bg-card/85">
            <CardContent className="space-y-2 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {card.title}
              </p>
              <VerticalScrollNumber
                value={`Rs ${formatAccountingAmount(card.value)}`}
                className="text-2xl font-semibold"
                durationMs={1000}
                staggerMs={30}
              />
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
        <Card className="bg-card/85">
          <CardHeader>
            <CardTitle>Sales vs Purchases</CardTitle>
          </CardHeader>
          <CardContent>
            <SalesPurchaseBarChart
              data={summary?.trend ?? []}
              period={period}
            />
          </CardContent>
        </Card>

        <Card className="bg-card/85">
          <CardHeader>
            <CardTitle>GST Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <GstPieChart data={summary?.gst_summary ?? []} />
          </CardContent>
        </Card>
      </div>

      {debugModeEnabled ? (
        <Card className="bg-card/85">
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
                            ? "border-red-200 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-200"
                            : entry.level === "warning"
                              ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200"
                              : entry.level === "success"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200"
                                : "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-700/20 dark:text-slate-200"
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
        accept=".jpeg,.jpg,.png,.pdf,.docx,.xlsx,.csv"
        className="hidden"
        onChange={(event) => {
          const selected = resolveSupportedFile(event.target.files?.[0] || null);
          if (!selected) {
            event.target.value = "";
            return;
          }
          void uploadFile(selected);
        }}
      />
      {aiChatOpen ? (
        <div className="fixed bottom-24 right-6 z-[60] w-[min(24rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-border bg-background shadow-2xl">
          <div className="flex items-center justify-between border-b border-border bg-background/95 px-4 py-3 backdrop-blur">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-primary/12 text-primary">
                <Sparkles className="h-4 w-4" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">AI Assistant</p>
                <p className="text-[11px] text-muted-foreground">Powered by {aiModelLabel}</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={onResetAIChat}
                aria-label="Reset chat"
                title="Reset chat"
              >
                <Sparkles className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setAiChatOpen(false)}
                aria-label="Close AI assistant"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="max-h-[50vh] space-y-3 overflow-y-auto bg-muted/25 px-3 py-3">
            {aiChatMessages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "max-w-[85%] rounded-xl px-3 py-2 shadow-sm",
                  message.role === "assistant"
                    ? "mr-auto border border-border bg-card text-foreground"
                    : "ml-auto bg-primary text-primary-foreground",
                )}
              >
                <p className="whitespace-pre-line text-sm leading-relaxed">{message.content}</p>
                <p
                  className={cn(
                    "mt-1 text-[10px]",
                    message.role === "assistant"
                      ? "text-muted-foreground"
                      : "text-primary-foreground/80",
                  )}
                >
                  {new Date(message.createdAt).toLocaleTimeString("en-IN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            ))}
            {aiChatThinking ? (
              <div className="mr-auto max-w-[85%] rounded-xl border border-border bg-card px-3 py-2 text-sm text-muted-foreground shadow-sm">
                AI is generating a concise answer...
              </div>
            ) : null}
            <div ref={aiChatEndRef} />
          </div>
          <div className="space-y-3 border-t border-border bg-background px-3 py-3">
            <div className="flex flex-wrap gap-2">
              {AI_DEFAULT_PROMPTS.map((promptOption) => (
                <button
                  key={promptOption}
                  type="button"
                  onClick={() => void sendAIMessage(promptOption)}
                  disabled={aiChatThinking}
                  className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {promptOption}
                </button>
              ))}
            </div>
            <form className="flex items-center gap-2" onSubmit={onSubmitAIChat}>
              <Input
                value={aiChatInput}
                onChange={(event) => setAiChatInput(event.target.value)}
                placeholder="Ask AI about your dashboard insights..."
                disabled={aiChatThinking}
              />
              <Button
                type="submit"
                size="icon"
                disabled={aiChatThinking || !aiChatInput.trim()}
                aria-label="Send AI message"
                title="Send"
              >
                {aiChatThinking ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </form>
          </div>
        </div>
      ) : null}
      <Button
        type="button"
        onClick={() => setAiChatOpen((previous) => !previous)}
        className="fixed bottom-24 right-6 z-50 h-12 w-12 rounded-full bg-sky-600 p-0 text-white shadow-lg hover:bg-sky-500 focus-visible:ring-sky-500"
        aria-label={aiChatOpen ? "Close AI Assistant chat" : "Open AI Assistant chat"}
        title="AI Assistant"
      >
        {!aiChatOpen ? (
          <span
            className="absolute inset-0 rounded-full bg-sky-400/60 animate-ping"
            aria-hidden="true"
          />
        ) : null}
        <Sparkles className="relative h-5 w-5" />
      </Button>
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
      <style jsx>{`
        @keyframes uploadMarqueeSlide {
          0% {
            transform: translateX(-120%);
          }
          100% {
            transform: translateX(320%);
          }
        }

        .upload-marquee-indicator {
          animation: uploadMarqueeSlide 1.05s linear infinite;
        }
      `}</style>
    </div>
  );
}

