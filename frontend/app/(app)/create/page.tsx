"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

export const dynamic = "force-dynamic";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";
import { formatAccountingAmount } from "@/lib/number-format";
import {
  INDIAN_STATES_AND_UTS,
  getStateCodeByName,
} from "@/lib/validation/business-details";
import {
  buildDefaultInvoiceNumber,
  buildIncrementedInvoiceNumber,
  formatFinancialYearInvoicePrefix,
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
};

type LatestCreatedInvoiceResponse = {
  invoice_number: string | null;
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
  quantity: "1",
  rate: "0",
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
  const searchParams = useSearchParams();
  const requestedClientId = searchParams.get("client_id") || "";

  const [clients, setClients] = useState<Client[]>([]);
  const [hsnSacMasters, setHsnSacMasters] = useState<HsnSacMasterEntry[]>([]);
  const [clientId, setClientId] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(
    new Date().toISOString().split("T")[0],
  );
  const [invoiceNumber, setInvoiceNumber] = useState(
    buildDefaultInvoiceNumber(new Date().toISOString().split("T")[0]),
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
  const invoiceDateRef = useRef(invoiceDate);

  useEffect(() => {
    invoiceDateRef.current = invoiceDate;
  }, [invoiceDate]);

  useEffect(() => {
    apiRequest<Client[]>("/clients")
      .then((data) => {
        setClients(data);
        if (
          requestedClientId &&
          data.some((client) => client.id === requestedClientId)
        ) {
          setClientId(requestedClientId);
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

    apiRequest<LatestCreatedInvoiceResponse>("/invoices/latest-created")
      .then((data) => {
        if (!active || invoiceNumberManuallyEditedRef.current) return;
        setInvoiceNumber(
          buildIncrementedInvoiceNumber(
            invoiceDateRef.current,
            data.invoice_number,
          ),
        );
      })
      .catch(() => {
        if (!active || invoiceNumberManuallyEditedRef.current) return;
        setInvoiceNumber(buildDefaultInvoiceNumber(invoiceDateRef.current));
      });

    return () => {
      active = false;
    };
  }, []);

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
    if (!invoiceDate) return "Invoice Date is required.";
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
    invoice_date: invoiceDate,
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

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${invoiceNumber}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
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
      alert("Invoice uploaded successfully.");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Upload failed");
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
        <Button asChild variant="outline">
          <Link href="/hsn-sac-master-list">HSN Master List</Link>
        </Button>
      </div>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Invoice Builder</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-1">
              <Label>Client</Label>
              <Select
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
              >
                <option value="">Select client</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Invoice Number</Label>
              <Input
                value={invoiceNumber}
                onChange={(event) => {
                  invoiceNumberManuallyEditedRef.current = true;
                  setInvoiceNumber(
                    sanitizeInvoiceNumberInput(event.target.value),
                  );
                }}
                placeholder="YYYY-YY/NNN"
                maxLength={11}
              />
            </div>
            <div className="space-y-1">
              <Label>Invoice Date</Label>
              <Input
                type="date"
                value={invoiceDate}
                onChange={(event) => {
                  const nextDate = event.target.value;
                  setInvoiceDate(nextDate);
                  setInvoiceNumber((previous) => {
                    if (!previous) return buildDefaultInvoiceNumber(nextDate);
                    const prefix = formatFinancialYearInvoicePrefix(nextDate);
                    if (validateInvoiceNumber(previous) === null) {
                      return `${prefix}/${previous.slice(8)}`;
                    }
                    return previous;
                  });
                }}
              />
            </div>
            <div className="space-y-1">
              <Label>Place of Supply</Label>
              <Select
                value={placeOfSupply}
                onChange={(event) => {
                  const selectedState = event.target.value;
                  setPlaceOfSupply(selectedState);
                  setPlaceOfSupplyCode(getStateCodeByName(selectedState) || "");
                }}
              >
                {INDIAN_STATES_AND_UTS.map((stateOption) => (
                  <option key={stateOption.name} value={stateOption.name}>
                    {stateOption.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Place of Supply Code</Label>
              <Input value={placeOfSupplyCode} readOnly />
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
                <p className="md:col-span-3">Description</p>
                <p className="md:col-span-2">HSN/SAC</p>
                <p className="md:col-span-2">Quantity</p>
                <p className="md:col-span-2">Rate</p>
                <p className="md:col-span-2">Tax Rate % </p>
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
                    />
                    <Select
                      className="md:col-span-2"
                      value={item.hsn_sac}
                      onChange={(event) =>
                        applyHsnSacMaster(index, event.target.value)
                      }
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
                      placeholder="Quantity"
                      value={item.quantity}
                      onChange={(event) =>
                        updateItem(
                          index,
                          "quantity",
                          sanitizeDecimalInput(event.target.value),
                        )
                      }
                    />
                    <Input
                      className="md:col-span-2"
                      placeholder="Rate (2 decimals)"
                      value={item.rate}
                      onChange={(event) =>
                        updateItem(
                          index,
                          "rate",
                          sanitizeDecimalInput(event.target.value),
                        )
                      }
                    />
                    <Input
                      className="md:col-span-2"
                      placeholder="0.00%"
                      value={item.tax_rate}
                      readOnly
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
