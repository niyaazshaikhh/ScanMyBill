"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays } from "lucide-react";

export const dynamic = "force-dynamic";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";
import { notifyApp } from "@/lib/app-notification";
import { formatIsoDateToDisplay, parseDisplayDateToIso, todayIsoDate } from "@/lib/date-format";
import { formatAccountingAmount } from "@/lib/number-format";
import { buildBillPdfFilename } from "@/lib/pdf-filename";
import {
  sanitizeDecimalInput,
  sanitizeItemDescriptionInput,
  toNumber,
  validateItemDescription,
  validateQuantity,
  validateRate,
} from "@/lib/validation/invoice";

type Client = {
  id: string;
  name: string;
};

type LatestCreatedDeliveryChallanResponse = {
  challan_number: number | null;
  order_number: string | null;
};

type LineItemInput = {
  description: string;
  quantity: string;
  rate: string;
};

type DeliveryChallanCreatePayload = {
  client_id: string;
  challan_number: number;
  order_number: string;
  challan_date: string;
  notes: string | null;
  items: Array<{
    description: string;
    quantity: number;
    rate: number;
  }>;
};

const INITIAL_ITEM: LineItemInput = {
  description: "",
  quantity: "",
  rate: "",
};

function buildIncrementedChallanNumber(latestChallanNumber: string | null | undefined): string {
  const candidate = (latestChallanNumber || "").trim();
  const previous = /^\d{1,5}$/.test(candidate) ? Number(candidate) : 0;
  const next = previous >= 99_999 ? 1 : previous + 1;
  return String(next);
}

function sanitizeChallanNumberInput(value: string): string {
  return value.replace(/\D/g, "").slice(0, 5);
}

function sanitizeIntegerInput(value: string): string {
  return value.replace(/\D/g, "");
}

function validateChallanNumber(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "Challan Number is required.";
  if (!/^\d+$/.test(trimmed)) return "Challan Number should be an integer.";
  if (Number(trimmed) <= 0) return "Challan Number should be greater than 0.";
  return null;
}

function validateOrderNumber(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "Order Number is required.";
  if (!/^\d{1,5}$/.test(trimmed)) return "Order Number should contain up to 5 digits.";
  return null;
}

function computeLineTotal(item: LineItemInput): number {
  return Math.round(toNumber(item.quantity) * toNumber(item.rate) * 100) / 100;
}

export default function CreateDeliveryChallanPage() {
  useAuthGuard();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedClientId = searchParams.get("client_id") || "";
  const initialChallanDateIso = todayIsoDate();

  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const [challanNumber, setChallanNumber] = useState("1");
  const [orderNumber, setOrderNumber] = useState("1");
  const [challanDate, setChallanDate] = useState(initialChallanDateIso);
  const [challanDateDisplay, setChallanDateDisplay] = useState(
    formatIsoDateToDisplay(initialChallanDateIso),
  );
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<LineItemInput[]>([{ ...INITIAL_ITEM }]);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const orderNumberManuallyEditedRef = useRef(false);
  const challanDatePickerRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    apiRequest<Client[]>("/clients")
      .then((data) => {
        setClients(data);
        if (
          requestedClientId
          && data.some((client) => client.id === requestedClientId)
        ) {
          setClientId(requestedClientId);
        }
      })
      .catch(() => setClients([]));
  }, [requestedClientId]);

  useEffect(() => {
    if (!clientId) {
      setOrderNumber("1");
      orderNumberManuallyEditedRef.current = false;
    } else {
      orderNumberManuallyEditedRef.current = false;
    }

    let active = true;
    const endpoint = clientId
      ? `/delivery-challans/latest-created?client_id=${encodeURIComponent(clientId)}`
      : "/delivery-challans/latest-created";

    apiRequest<LatestCreatedDeliveryChallanResponse>(endpoint)
      .then((data) => {
        if (!active) return;
        setChallanNumber(String((data.challan_number ?? 0) + 1));
        if (!orderNumberManuallyEditedRef.current) {
          if (clientId) {
            setOrderNumber(buildIncrementedChallanNumber(data.order_number));
          } else {
            setOrderNumber("1");
          }
        }
      })
      .catch(() => {
        if (!active) return;
        setChallanNumber("1");
        if (!orderNumberManuallyEditedRef.current) {
          setOrderNumber("1");
        }
      });

    return () => {
      active = false;
    };
  }, [clientId]);

  const updateItem = (index: number, key: keyof LineItemInput, value: string) => {
    setItems((prev) =>
      prev.map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        return { ...item, [key]: value };
      }),
    );
  };

  const addItem = () => {
    setItems((prev) => [...prev, { ...INITIAL_ITEM }]);
  };

  const removeItem = (index: number) => {
    setItems((prev) => prev.filter((_, itemIndex) => itemIndex !== index));
  };

  const applyChallanDate = (nextDate: string) => {
    setChallanDate(nextDate);
    setChallanDateDisplay(formatIsoDateToDisplay(nextDate));
  };

  const subtotal = useMemo(
    () => items.reduce((total, item) => total + computeLineTotal(item), 0),
    [items],
  );

  const validateLine = (item: LineItemInput, index: number): string | null => {
    const descriptionError = validateItemDescription(item.description);
    if (descriptionError) return `Row ${index + 1}: ${descriptionError}`;

    const quantityError = validateQuantity(item.quantity);
    if (quantityError) return `Row ${index + 1}: ${quantityError}`;

    const rateError = validateRate(item.rate);
    if (rateError) return `Row ${index + 1}: ${rateError}`;

    return null;
  };

  const validateForm = (): string | null => {
    if (!clientId) return "Client is required.";
    const challanNumberError = validateChallanNumber(challanNumber);
    if (challanNumberError) return challanNumberError;
    const orderNumberError = validateOrderNumber(orderNumber);
    if (orderNumberError) return orderNumberError;

    if (!challanDateDisplay.trim()) return "Challan Date is required.";
    const parsedChallanDate = parseDisplayDateToIso(challanDateDisplay);
    if (!parsedChallanDate) return "Challan Date should be in DD/MMM/YYYY format.";

    if (!items.length) return "At least one item is required.";
    for (let index = 0; index < items.length; index += 1) {
      const lineError = validateLine(items[index], index);
      if (lineError) return lineError;
    }

    return null;
  };

  const buildPayload = (): DeliveryChallanCreatePayload => ({
    client_id: clientId,
    challan_number: Number(challanNumber),
    order_number: orderNumber.trim(),
    challan_date: parseDisplayDateToIso(challanDateDisplay) || challanDate,
    notes: notes.trim() || null,
    items: items.map((item) => ({
      description: item.description.trim(),
      quantity: toNumber(item.quantity),
      rate: toNumber(item.rate),
    })),
  });

  const exportPdf = async () => {
    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setExporting(true);
    setFormError(null);
    try {
      const blob = await apiRequest<Blob>("/delivery-challans/create/pdf", {
        method: "POST",
        body: buildPayload(),
        responseType: "blob",
      });

      const billDateIso = parseDisplayDateToIso(challanDateDisplay) || challanDate;
      const clientName = clients.find((client) => client.id === clientId)?.name || "Client";
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = buildBillPdfFilename({
        billDateIso,
        documentNumber: challanNumber,
        clientName,
      });
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "PDF export failed");
    } finally {
      setExporting(false);
    }
  };

  const uploadChallan = async () => {
    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setSaving(true);
    setFormError(null);
    try {
      await apiRequest("/delivery-challans/create", {
        method: "POST",
        body: buildPayload(),
      });
      notifyApp({
        title: "Delivery challan uploaded successfully",
        message: "Delivery challan uploaded successfully",
        tone: "success",
      });
      const endpoint = clientId
        ? `/delivery-challans/latest-created?client_id=${encodeURIComponent(clientId)}`
        : "/delivery-challans/latest-created";
      const latest = await apiRequest<LatestCreatedDeliveryChallanResponse>(endpoint);
      setChallanNumber(String((latest.challan_number ?? 0) + 1));
      orderNumberManuallyEditedRef.current = false;
      setOrderNumber(buildIncrementedChallanNumber(latest.order_number));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setFormError(message);
      notifyApp({
        title: "Delivery challan upload failed",
        message,
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-[var(--font-space)] text-2xl font-semibold">
            Create Delivery Challan
          </h2>
          <p className="text-sm text-muted-foreground">
            Create delivery challans and save them for later download.
          </p>
        </div>
        <div className="min-w-44 space-y-1">
          <Label className="text-xs">Challan Type</Label>
          <Select
            value="delivery"
            onChange={(event) => {
              if (event.target.value === "gst") {
                router.push("/create");
              }
            }}
          >
            <option value="gst">GST Challan</option>
            <option value="delivery">Delivery Challan</option>
          </Select>
        </div>
      </div>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Challan Builder</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="space-y-1">
              <Label>
                Client <span className="text-destructive">*</span>
              </Label>
              <Select value={clientId} onChange={(event) => setClientId(event.target.value)} required>
                <option value="">Select client</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>
                Order Number <span className="text-destructive">*</span>
              </Label>
              <Input
                value={orderNumber}
                onChange={(event) => {
                  orderNumberManuallyEditedRef.current = true;
                  setOrderNumber(sanitizeChallanNumberInput(event.target.value));
                }}
                placeholder="1"
                maxLength={5}
                required
              />
            </div>
            <div className="space-y-1">
              <Label>
                Challan Number <span className="text-destructive">*</span>
              </Label>
              <Input
                type="text"
                inputMode="numeric"
                pattern="\d*"
                value={challanNumber}
                onChange={(event) => setChallanNumber(sanitizeIntegerInput(event.target.value))}
                placeholder="1"
                required
              />
            </div>
            <div className="space-y-1">
              <Label>
                Challan Date <span className="text-destructive">*</span>
              </Label>
              <div className="flex gap-2">
                <Input
                  type="text"
                  value={challanDateDisplay}
                  onChange={(event) => {
                    const nextDisplayDate = event.target.value;
                    setChallanDateDisplay(nextDisplayDate);
                    const nextDate = parseDisplayDateToIso(nextDisplayDate);
                    if (!nextDate) return;
                    applyChallanDate(nextDate);
                  }}
                  placeholder="DD/MMM/YYYY"
                  required
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    const picker = challanDatePickerRef.current;
                    if (!picker) return;
                    if ("showPicker" in picker) {
                      (picker as HTMLInputElement & { showPicker: () => void }).showPicker();
                    } else {
                      picker.click();
                    }
                  }}
                  aria-label="Pick challan date"
                  title="Pick challan date"
                >
                  <CalendarDays className="h-4 w-4" />
                </Button>
                <input
                  ref={challanDatePickerRef}
                  type="date"
                  value={challanDate}
                  onChange={(event) => {
                    const nextDate = event.target.value;
                    if (!nextDate) return;
                    applyChallanDate(nextDate);
                  }}
                  className="sr-only"
                  tabIndex={-1}
                  aria-hidden="true"
                />
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Items</h3>
              <Button variant="outline" onClick={addItem}>
                + Add Item
              </Button>
            </div>

            <div className="space-y-3">
              <div className="hidden gap-2 px-1 text-xs font-medium text-muted-foreground md:grid md:grid-cols-8">
                <p className="md:col-span-3">
                  Description <span className="text-destructive">*</span>
                </p>
                <p className="md:col-span-2">
                  Quantity <span className="text-destructive">*</span>
                </p>
                <p className="md:col-span-2">
                  Rate <span className="text-destructive">*</span>
                </p>
              </div>
              {items.map((item, index) => (
                <div
                  key={index}
                  className="space-y-2 rounded-md border border-border bg-background p-3"
                >
                  <div className="grid gap-2 md:grid-cols-8">
                    <div className="space-y-1 md:col-span-3">
                      <Label className="text-xs md:hidden">
                        Description <span className="text-destructive">*</span>
                      </Label>
                      <Input
                        placeholder="Description (Max 20)"
                        value={item.description}
                        onChange={(event) =>
                          updateItem(
                            index,
                            "description",
                            sanitizeItemDescriptionInput(event.target.value),
                          )
                        }
                        maxLength={20}
                        required
                      />
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <Label className="text-xs md:hidden">
                        Quantity <span className="text-destructive">*</span>
                      </Label>
                      <Input
                        placeholder="0"
                        value={item.quantity}
                        onChange={(event) =>
                          updateItem(index, "quantity", sanitizeDecimalInput(event.target.value))
                        }
                        required
                      />
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <Label className="text-xs md:hidden">
                        Rate <span className="text-destructive">*</span>
                      </Label>
                      <Input
                        placeholder="0"
                        value={item.rate}
                        onChange={(event) =>
                          updateItem(index, "rate", sanitizeDecimalInput(event.target.value))
                        }
                        required
                      />
                    </div>
                    <Button
                      variant="destructive"
                      className="md:col-span-1"
                      onClick={() => removeItem(index)}
                      disabled={items.length === 1}
                    >
                      X
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Amount: Rs {formatAccountingAmount(computeLineTotal(item))}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-border bg-muted/20 p-4">
            <p className="font-semibold">
              Subtotal: Rs {formatAccountingAmount(subtotal)}
            </p>
          </div>

          <div className="space-y-1">
            <Label>Note</Label>
            <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>

          {formError ? <p className="text-sm text-destructive">{formError}</p> : null}

          <div className="flex flex-col gap-3 sm:flex-row">
            <Button onClick={exportPdf} variant="outline" disabled={saving || exporting}>
              {exporting ? "Exporting..." : "Export (PDF)"}
            </Button>
            <Button onClick={uploadChallan} disabled={saving || exporting}>
              {saving ? "Uploading..." : "Upload (Save in DB)"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
