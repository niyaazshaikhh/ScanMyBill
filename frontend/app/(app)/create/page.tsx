"use client";

import Link from "next/link";
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
  INDIAN_STATES_AND_UTS,
  getStateCodeByName,
  validateOptionalGstin,
} from "@/lib/validation/business-details";
import {
  buildDefaultInvoiceNumber,
  buildIncrementedInvoiceNumber,
  sanitizeDecimalInput,
  sanitizeInvoiceNumberInput,
  sanitizeItemDescriptionInput,
  toNumber,
  validateHsnSac,
  validateInvoiceNumber,
  validateItemDescription,
  validateQuantity,
  validateRate,
  validateTaxRate,
} from "@/lib/validation/invoice";

type Client = {
  id: string;
  name: string;
  gst_number?: string | null;
};

type LatestCreatedInvoiceResponse = {
  invoice_number: string | null;
};

type PersonalDetailsResponse = {
  state_name: string | null;
};

type HsnSacMasterEntry = {
  id: string;
  description: string;
  hsn_sac_code: string;
  tax_rate: number;
  created_at: string;
};

type LineItemInput = {
  description: string;
  hsn_sac: string;
  quantity: string;
  rate: string;
  tax_rate: string;
};

type InvoiceCreatePayload = {
  client_id: string;
  invoice_number: string;
  invoice_date: string;
  place_of_supply: string;
  place_of_supply_code: string;
  notes: string | null;
  items: Array<{
    description: string;
    hsn_sac: string;
    quantity: number;
    rate: number;
    tax_rate: number;
  }>;
};

type LineItemComputed = {
  amountBeforeTax: number;
  cgst: number;
  sgstUtgst: number;
  totalTaxAmount: number;
  grandTotal: number;
};

const INITIAL_ITEM: LineItemInput = {
  description: "",
  hsn_sac: "",
  quantity: "",
  rate: "",
  tax_rate: "",
};

const DEFAULT_PLACE_OF_SUPPLY = "Maharashtra";
const DEFAULT_PLACE_OF_SUPPLY_CODE =
  getStateCodeByName(DEFAULT_PLACE_OF_SUPPLY) || "27";

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatTaxRateInput(value: number): string {
  return value
    .toFixed(2)
    .replace(/\.00$/, "")
    .replace(/(\.\d)0$/, "$1");
}

function MandatoryMark() {
  return <span className="text-destructive">*</span>;
}

function computeLine(item: LineItemInput): LineItemComputed {
  const quantity = toNumber(item.quantity);
  const rate = toNumber(item.rate);
  const taxRate = toNumber(item.tax_rate);
  const amountBeforeTax = quantity * rate;
  const totalTaxAmount = amountBeforeTax * (taxRate / 100);
  const cgst = totalTaxAmount / 2;
  const sgstUtgst = totalTaxAmount / 2;
  const grandTotal = amountBeforeTax + totalTaxAmount;
  return {
    amountBeforeTax: round2(amountBeforeTax),
    cgst: round2(cgst),
    sgstUtgst: round2(sgstUtgst),
    totalTaxAmount: round2(totalTaxAmount),
    grandTotal: round2(grandTotal),
  };
}

export default function CreateInvoicePage() {
  useAuthGuard();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedClientId = searchParams.get("client_id") || "";
  const initialInvoiceDateIso = todayIsoDate();

  const [clients, setClients] = useState<Client[]>([]);
  const [hsnSacMasters, setHsnSacMasters] = useState<HsnSacMasterEntry[]>([]);
  const [clientId, setClientId] = useState("");
  const [defaultClientId, setDefaultClientId] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(initialInvoiceDateIso);
  const [invoiceDateDisplay, setInvoiceDateDisplay] = useState(
    formatIsoDateToDisplay(initialInvoiceDateIso),
  );
  const [invoiceNumber, setInvoiceNumber] = useState(
    buildDefaultInvoiceNumber(initialInvoiceDateIso),
  );
  const [placeOfSupply, setPlaceOfSupply] = useState(DEFAULT_PLACE_OF_SUPPLY);
  const [placeOfSupplyCode, setPlaceOfSupplyCode] = useState(
    DEFAULT_PLACE_OF_SUPPLY_CODE,
  );
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<LineItemInput[]>([{ ...INITIAL_ITEM }]);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const invoiceNumberManuallyEditedRef = useRef(false);
  const placeOfSupplyManuallyEditedRef = useRef(false);
  const [defaultPlaceOfSupply, setDefaultPlaceOfSupply] = useState(DEFAULT_PLACE_OF_SUPPLY);
  const [defaultPlaceOfSupplyCode, setDefaultPlaceOfSupplyCode] = useState(DEFAULT_PLACE_OF_SUPPLY_CODE);
  const [invoiceNumberRefreshNonce, setInvoiceNumberRefreshNonce] = useState(0);
  const invoiceDatePickerRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    apiRequest<Client[]>("/clients")
      .then((data) => {
        const gstEnabledClients = data.filter(
          (client) =>
            typeof client.gst_number === "string" &&
            client.gst_number.trim().length > 0 &&
            validateOptionalGstin(client.gst_number.trim().toUpperCase()) === null,
        );
        setClients(gstEnabledClients);
        if (
          requestedClientId &&
          gstEnabledClients.some((client) => client.id === requestedClientId)
        ) {
          setDefaultClientId(requestedClientId);
          setClientId(requestedClientId);
        } else if (requestedClientId) {
          setDefaultClientId("");
          setClientId("");
        }
      })
      .catch(() => setClients([]));
  }, [requestedClientId]);

  useEffect(() => {
    let active = true;
    apiRequest<HsnSacMasterEntry[]>("/hsn-sac-master-list")
      .then((data) => {
        if (!active) return;
        setHsnSacMasters(data);
      })
      .catch(() => {
        if (!active) return;
        setHsnSacMasters([]);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    apiRequest<PersonalDetailsResponse>("/users/personal-details")
      .then((details) => {
        if (!active || placeOfSupplyManuallyEditedRef.current) return;
        const configuredState = (details.state_name || "").trim();
        if (!configuredState) return;
        const configuredStateCode = getStateCodeByName(configuredState);
        if (!configuredStateCode) return;
        setDefaultPlaceOfSupply(configuredState);
        setDefaultPlaceOfSupplyCode(configuredStateCode);
        setPlaceOfSupply(configuredState);
        setPlaceOfSupplyCode(configuredStateCode);
      })
      .catch(() => {
        // Keep existing defaults if personal details are unavailable.
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    apiRequest<LatestCreatedInvoiceResponse>(
      `/invoices/latest-created?invoice_date=${encodeURIComponent(invoiceDate)}`,
    )
      .then((data) => {
        if (!active || invoiceNumberManuallyEditedRef.current) return;
        setInvoiceNumber(buildIncrementedInvoiceNumber(invoiceDate, data.invoice_number));
      })
      .catch(() => {
        if (!active || invoiceNumberManuallyEditedRef.current) return;
        setInvoiceNumber(buildDefaultInvoiceNumber(invoiceDate));
      });

    return () => {
      active = false;
    };
  }, [invoiceDate, invoiceNumberRefreshNonce]);

  const resetFormToDefaults = () => {
    const nextInvoiceDate = todayIsoDate();
    invoiceNumberManuallyEditedRef.current = false;
    placeOfSupplyManuallyEditedRef.current = false;
    setFormError(null);
    setClientId(defaultClientId);
    setInvoiceDate(nextInvoiceDate);
    setInvoiceDateDisplay(formatIsoDateToDisplay(nextInvoiceDate));
    setInvoiceNumber(buildDefaultInvoiceNumber(nextInvoiceDate));
    setPlaceOfSupply(defaultPlaceOfSupply);
    setPlaceOfSupplyCode(defaultPlaceOfSupplyCode);
    setNotes("");
    setItems([{ ...INITIAL_ITEM }]);
    setInvoiceNumberRefreshNonce((previous) => previous + 1);
  };

  const computedLines = useMemo(
    () => items.map((item) => computeLine(item)),
    [items],
  );

  const totals = useMemo(() => {
    let amountBeforeTax = 0;
    let cgst = 0;
    let sgstUtgst = 0;
    let totalTaxAmount = 0;
    let grandTotal = 0;

    computedLines.forEach((line) => {
      amountBeforeTax += line.amountBeforeTax;
      cgst += line.cgst;
      sgstUtgst += line.sgstUtgst;
      totalTaxAmount += line.totalTaxAmount;
      grandTotal += line.grandTotal;
    });

    return {
      amountBeforeTax: round2(amountBeforeTax),
      cgst: round2(cgst),
      sgstUtgst: round2(sgstUtgst),
      totalTaxAmount: round2(totalTaxAmount),
      grandTotal: round2(grandTotal),
    };
  }, [computedLines]);

  const updateItem = (
    index: number,
    key: keyof LineItemInput,
    value: string,
  ) => {
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

  const applyHsnSacMaster = (index: number, hsnSacCode: string) => {
    const selectedMaster = hsnSacMasters.find(
      (entry) => entry.hsn_sac_code === hsnSacCode,
    );

    setItems((prev) =>
      prev.map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        return {
          ...item,
          hsn_sac: hsnSacCode,
          tax_rate: selectedMaster
            ? formatTaxRateInput(selectedMaster.tax_rate)
            : "",
        };
      }),
    );
  };

  const applyInvoiceDate = (nextDate: string) => {
    setInvoiceDate(nextDate);
    setInvoiceDateDisplay(formatIsoDateToDisplay(nextDate));
    if (!invoiceNumberManuallyEditedRef.current) {
      setInvoiceNumber(buildDefaultInvoiceNumber(nextDate));
    }
  };

  const validateLine = (item: LineItemInput, index: number): string | null => {
    const descriptionError = validateItemDescription(item.description);
    if (descriptionError) return `Row ${index + 1}: ${descriptionError}`;

    const hsnError = validateHsnSac(item.hsn_sac);
    if (hsnError) return `Row ${index + 1}: ${hsnError}`;

    const quantityError = validateQuantity(item.quantity);
    if (quantityError) return `Row ${index + 1}: ${quantityError}`;

    const rateError = validateRate(item.rate);
    if (rateError) return `Row ${index + 1}: ${rateError}`;

    const taxRateError = validateTaxRate(item.tax_rate);
    if (taxRateError) return `Row ${index + 1}: ${taxRateError}`;

    return null;
  };

  const validateForm = (): string | null => {
    if (!clientId) return "Client is required.";
    if (!invoiceDateDisplay.trim()) return "Invoice Date is required.";
    const parsedInvoiceDate = parseDisplayDateToIso(invoiceDateDisplay);
    if (!parsedInvoiceDate) return "Invoice Date should be in DD/MMM/YYYY format.";
    if (!placeOfSupply) return "Place of Supply is required.";
    if (!placeOfSupplyCode) return "Place of Supply Code is required.";

    const invoiceNumberError = validateInvoiceNumber(invoiceNumber);
    if (invoiceNumberError) return invoiceNumberError;

    if (!items.length) return "At least one item is required.";
    for (let index = 0; index < items.length; index += 1) {
      const lineError = validateLine(items[index], index);
      if (lineError) return lineError;
    }

    return null;
  };

  const buildInvoicePayload = (): InvoiceCreatePayload => ({
    client_id: clientId,
    invoice_number: invoiceNumber.trim(),
    invoice_date: parseDisplayDateToIso(invoiceDateDisplay) || invoiceDate,
    place_of_supply: placeOfSupply,
    place_of_supply_code: placeOfSupplyCode,
    notes: notes.trim() || null,
    items: items.map((item) => ({
      description: item.description.trim(),
      hsn_sac: item.hsn_sac.trim(),
      quantity: toNumber(item.quantity),
      rate: toNumber(item.rate),
      tax_rate: toNumber(item.tax_rate),
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
      const blob = await apiRequest<Blob>("/invoices/create/pdf", {
        method: "POST",
        body: buildInvoicePayload(),
        responseType: "blob",
      });

      const billDateIso = parseDisplayDateToIso(invoiceDateDisplay) || invoiceDate;
      const clientName = clients.find((client) => client.id === clientId)?.name || "Client";
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = buildBillPdfFilename({
        billDateIso,
        documentNumber: invoiceNumber,
        clientName,
      });
      link.click();
      URL.revokeObjectURL(url);
      resetFormToDefaults();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "PDF export failed");
    } finally {
      setExporting(false);
    }
  };

  const uploadInvoice = async () => {
    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setSaving(true);
    setFormError(null);
    try {
      await apiRequest("/invoices/create", {
        method: "POST",
        body: buildInvoicePayload(),
      });
      notifyApp({
        title: "Invoice uploaded successfully",
        message: "Invoice uploaded successfully",
        tone: "success",
      });
      resetFormToDefaults();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setFormError(message);
      notifyApp({
        title: "Invoice upload failed",
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
            Create Invoice
          </h2>
          <p className="text-sm text-muted-foreground">
            Create sales invoices with automatic tax split calculations.
          </p>
        </div>
        <div className="flex w-full flex-wrap items-end gap-2 sm:w-auto sm:justify-end">
          <Button asChild variant="outline">
            <Link href="/hsn-sac-master-list">HSN Master List</Link>
          </Button>
          <div className="w-full space-y-1 sm:min-w-44 sm:w-auto">
            <Label className="text-xs">Challan Type</Label>
            <Select
              value="gst"
              onChange={(event) => {
                if (event.target.value === "delivery") {
                  router.push("/create/delivery-challan");
                }
              }}
            >
              <option value="gst">GST Challan</option>
              <option value="delivery">Delivery Challan</option>
            </Select>
          </div>
        </div>
      </div>

      <Card className="bg-card/85">
        <CardHeader>
          <CardTitle>Invoice Builder</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-1">
              <Label>
                Client <MandatoryMark />
              </Label>
              <Select
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
                required
              >
                <option value="">
                  {clients.length ? "Select client" : "No clients with GST Number"}
                </option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>
                Invoice Number <MandatoryMark />
              </Label>
              <Input
                value={invoiceNumber}
                onChange={(event) => {
                  invoiceNumberManuallyEditedRef.current = true;
                  setInvoiceNumber(
                    sanitizeInvoiceNumberInput(event.target.value),
                  );
                }}
                placeholder="Ex: 2024-25/001 or INV#001"
                maxLength={20}
                required
              />
            </div>
            <div className="space-y-1">
              <Label>
                Invoice Date <MandatoryMark />
              </Label>
              <div className="flex gap-2">
                <Input
                  type="text"
                  value={invoiceDateDisplay}
                  onChange={(event) => {
                    const nextDisplayDate = event.target.value;
                    setInvoiceDateDisplay(nextDisplayDate);
                    const nextDate = parseDisplayDateToIso(nextDisplayDate);
                    if (!nextDate) return;
                    applyInvoiceDate(nextDate);
                  }}
                  placeholder="DD/MMM/YYYY"
                  required
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    const picker = invoiceDatePickerRef.current;
                    if (!picker) return;
                    const pickerWithShow = picker as HTMLInputElement & { showPicker?: () => void };
                    if (typeof pickerWithShow.showPicker === "function") {
                      pickerWithShow.showPicker();
                      return;
                    }
                    picker.click();
                  }}
                  aria-label="Pick invoice date"
                  title="Pick invoice date"
                >
                  <CalendarDays className="h-4 w-4" />
                </Button>
                <input
                  ref={invoiceDatePickerRef}
                  type="date"
                  value={invoiceDate}
                  onChange={(event) => {
                    const nextDate = event.target.value;
                    if (!nextDate) return;
                    applyInvoiceDate(nextDate);
                  }}
                  className="sr-only"
                  tabIndex={-1}
                  aria-hidden="true"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>
                Place of Supply <MandatoryMark />
              </Label>
              <Select
                value={placeOfSupply}
                onChange={(event) => {
                  placeOfSupplyManuallyEditedRef.current = true;
                  const selectedState = event.target.value;
                  setPlaceOfSupply(selectedState);
                  setPlaceOfSupplyCode(getStateCodeByName(selectedState) || "");
                }}
                required
              >
                {INDIAN_STATES_AND_UTS.map((stateOption) => (
                  <option key={stateOption.name} value={stateOption.name}>
                    {stateOption.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>
                Place of Supply Code <MandatoryMark />
              </Label>
              <Input value={placeOfSupplyCode} readOnly required />
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Items</h3>
              <Button variant="outline" onClick={addItem}>
                + Add Item
              </Button>
            </div>
            {hsnSacMasters.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Add HSN/SAC entries in{" "}
                <Link className="underline" href="/hsn-sac-master-list">
                  Master List
                </Link>{" "}
                to use the dropdown.
              </p>
            ) : null}

            <div className="space-y-3">
              <div className="hidden gap-2 px-1 text-xs font-medium text-muted-foreground md:grid md:grid-cols-12">
                <p className="md:col-span-3">
                  Description <MandatoryMark />
                </p>
                <p className="md:col-span-2">
                  HSN/SAC <MandatoryMark />
                </p>
                <p className="md:col-span-2">
                  Quantity <MandatoryMark />
                </p>
                <p className="md:col-span-2">
                  Rate <MandatoryMark />
                </p>
                <p className="md:col-span-2">
                  Tax Rate % <MandatoryMark />
                </p>
              </div>
              {items.map((item, index) => (
                <div
                  key={index}
                  className="space-y-2 rounded-md border border-border bg-background p-3"
                >
                  <div className="grid gap-2 md:grid-cols-12">
                    <Input
                      className="md:col-span-3"
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
                    <Select
                      className="md:col-span-2"
                      value={item.hsn_sac}
                      onChange={(event) =>
                        applyHsnSacMaster(index, event.target.value)
                      }
                      required
                    >
                      <option value="">Select HSN/SAC</option>
                      {hsnSacMasters.map((entry) => (
                        <option key={entry.id} value={entry.hsn_sac_code}>
                          {`${entry.description}-${entry.hsn_sac_code} - ${formatTaxRateInput(entry.tax_rate)}%`}
                        </option>
                      ))}
                    </Select>
                    <Input
                      className="md:col-span-2"
                      placeholder="0"
                      value={item.quantity}
                      onChange={(event) =>
                        updateItem(
                          index,
                          "quantity",
                          sanitizeDecimalInput(event.target.value),
                        )
                      }
                      required
                    />
                    <Input
                      className="md:col-span-2"
                      placeholder="0"
                      value={item.rate}
                      onChange={(event) =>
                        updateItem(
                          index,
                          "rate",
                          sanitizeDecimalInput(event.target.value),
                        )
                      }
                      required
                    />
                    <Input
                      className="md:col-span-2"
                      placeholder="0.00%"
                      value={item.tax_rate}
                      readOnly
                      required
                    />
                    <Button
                      variant="destructive"
                      className="md:col-span-1"
                      onClick={() => removeItem(index)}
                      disabled={items.length === 1}
                    >
                      X
                    </Button>
                  </div>
                  <div className="grid gap-2 text-xs text-muted-foreground md:grid-cols-5">
                    <p>
                      Amount: Rs{" "}
                      {formatAccountingAmount(
                        computedLines[index].amountBeforeTax,
                      )}
                    </p>
                    <p>
                      CGST: Rs{" "}
                      {formatAccountingAmount(computedLines[index].cgst)}
                    </p>
                    <p>
                      SGST/UTGST: Rs{" "}
                      {formatAccountingAmount(computedLines[index].sgstUtgst)}
                    </p>
                    <p>
                      Total Tax: Rs{" "}
                      {formatAccountingAmount(
                        computedLines[index].totalTaxAmount,
                      )}
                    </p>
                    <p className="font-medium text-foreground">
                      Grand Total: Rs{" "}
                      {formatAccountingAmount(computedLines[index].grandTotal)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-3 rounded-md border border-border bg-muted/20 p-4 md:grid-cols-5">
            <p>Amount: Rs {formatAccountingAmount(totals.amountBeforeTax)}</p>
            <p>CGST: Rs {formatAccountingAmount(totals.cgst)}</p>
            <p>SGST/UTGST: Rs {formatAccountingAmount(totals.sgstUtgst)}</p>
            <p>
              Total Tax Amount: Rs{" "}
              {formatAccountingAmount(totals.totalTaxAmount)}
            </p>
            <p className="font-semibold">
              Grand Total: Rs {formatAccountingAmount(totals.grandTotal)}
            </p>
          </div>

          <div className="space-y-1">
            <Label>Note</Label>
            <Textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>

          {formError ? (
            <p className="text-sm text-destructive">{formError}</p>
          ) : null}

          <div className="flex flex-col gap-3 sm:flex-row">
            <Button
              onClick={exportPdf}
              variant="outline"
              disabled={saving || exporting}
            >
              {exporting ? "Exporting..." : "Export (PDF)"}
            </Button>
            <Button onClick={uploadInvoice} disabled={saving || exporting}>
              {saving ? "Uploading..." : "Upload (Save in DB)"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

