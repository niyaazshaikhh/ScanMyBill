"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

export const dynamic = "force-dynamic";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuthGuard } from "@/hooks/useAuthGuard";
import { apiRequest } from "@/lib/api";

type HsnSacMasterEntry = {
  id: string;
  description: string;
  hsn_sac_code: string;
  tax_rate: number;
  created_at: string;
};

type HsnSacMasterForm = {
  description: string;
  hsn_sac_code: string;
  tax_rate: string;
};

const EMPTY_FORM: HsnSacMasterForm = {
  description: "",
  hsn_sac_code: "",
  tax_rate: "",
};

const TAX_RATE_PATTERN = /^\d+(\.\d{1,2})?$/;

function sanitizeDescriptionInput(value: string): string {
  return value.slice(0, 15);
}

function sanitizeHsnSacCodeInput(value: string): string {
  return value.replace(/\D/g, "").slice(0, 15);
}

function sanitizeTaxRateInput(value: string): string {
  const sanitized = value.replace(/[^0-9.]/g, "");
  const [whole = "", fraction = ""] = sanitized.split(".");
  if (!sanitized.includes(".")) return whole;
  return `${whole}.${fraction.slice(0, 2)}`;
}

function formatTaxRate(value: number): string {
  return value
    .toFixed(2)
    .replace(/\.00$/, "")
    .replace(/(\.\d)0$/, "$1");
}

function validateForm(form: HsnSacMasterForm): string | null {
  const description = form.description.trim();
  if (!description) return "Description is required.";
  if (description.length > 15) return "Description should be up to 15 characters only.";

  if (!/^\d{4,15}$/.test(form.hsn_sac_code)) {
    return "HSN/SAC code should contain 4 to 15 digits.";
  }

  const taxRate = form.tax_rate.trim();
  if (!taxRate) return "Associated tax rate is required.";
  if (!TAX_RATE_PATTERN.test(taxRate)) return "Tax Rate should be a number with up to 2 decimal places.";
  const numericTaxRate = Number(taxRate);
  if (!Number.isFinite(numericTaxRate) || numericTaxRate < 0 || numericTaxRate > 99.99) {
    return "Tax Rate should be between 0 and 99.99.";
  }

  return null;
}

export default function HsnSacMasterListPage() {
  useAuthGuard();

  const [entries, setEntries] = useState<HsnSacMasterEntry[]>([]);
  const [form, setForm] = useState<HsnSacMasterForm>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadEntries = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<HsnSacMasterEntry[]>("/hsn-sac-master-list");
      setEntries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load HSN/SAC master list.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadEntries();
  }, [loadEntries]);

  const sortedEntries = useMemo(() => {
    return [...entries].sort((left, right) =>
      left.description.localeCompare(right.description, undefined, {
        sensitivity: "base",
      }),
    );
  }, [entries]);

  const onCreate = async () => {
    setMessage(null);
    const validationError = validateForm(form);
    if (validationError) {
      setError(validationError);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await apiRequest("/hsn-sac-master-list", {
        method: "POST",
        body: {
          description: form.description.trim(),
          hsn_sac_code: form.hsn_sac_code,
          tax_rate: Number(form.tax_rate),
        },
      });
      setForm(EMPTY_FORM);
      setMessage("HSN/SAC master entry saved.");
      await loadEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save HSN/SAC master entry.");
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (entryId: string) => {
    const shouldDelete = window.confirm("Delete this HSN/SAC entry?");
    if (!shouldDelete) return;

    setDeletingId(entryId);
    setMessage(null);
    setError(null);
    try {
      await apiRequest(`/hsn-sac-master-list/${entryId}`, { method: "DELETE" });
      setMessage("HSN/SAC master entry deleted.");
      await loadEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete HSN/SAC master entry.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-[var(--font-space)] text-2xl font-semibold">
            HSN/SAC Master List
          </h2>
          <p className="text-sm text-muted-foreground">
            Manage reusable HSN/SAC codes for invoice creation.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/create">Back to Create</Link>
        </Button>
      </div>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Add Entry</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="master-description">
                Description <span className="text-destructive">*</span>
              </Label>
              <Input
                id="master-description"
                value={form.description}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    description: sanitizeDescriptionInput(event.target.value),
                  }))
                }
                maxLength={15}
                placeholder="Short code name"
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="master-hsn">
                HSN/SAC Code <span className="text-destructive">*</span>
              </Label>
              <Input
                id="master-hsn"
                value={form.hsn_sac_code}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    hsn_sac_code: sanitizeHsnSacCodeInput(event.target.value),
                  }))
                }
                maxLength={15}
                minLength={4}
                placeholder="Enter HSN/SAC code"
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="master-tax">
                Associated Tax Rate % <span className="text-destructive">*</span>
              </Label>
              <Input
                id="master-tax"
                value={form.tax_rate}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    tax_rate: sanitizeTaxRateInput(event.target.value),
                  }))
                }
                placeholder="0.00"
                required
              />
            </div>
          </div>
          <Button onClick={onCreate} disabled={saving}>
            {saving ? "Saving..." : "Save Entry"}
          </Button>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
        </CardContent>
      </Card>

      <Card className="bg-white/85">
        <CardHeader>
          <CardTitle>Saved Entries</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? <p className="text-sm text-muted-foreground">Loading entries...</p> : null}
          {!loading ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Description</TableHead>
                  <TableHead>HSN/SAC</TableHead>
                  <TableHead>Tax Rate %</TableHead>
                  <TableHead>Dropdown Value Preview</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedEntries.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      No HSN/SAC master entries yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedEntries.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell>{entry.description}</TableCell>
                      <TableCell>{entry.hsn_sac_code}</TableCell>
                      <TableCell>{formatTaxRate(entry.tax_rate)}</TableCell>
                      <TableCell>{`${entry.description}-${entry.hsn_sac_code} - ${formatTaxRate(entry.tax_rate)}%`}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => onDelete(entry.id)}
                          disabled={deletingId === entry.id}
                        >
                          {deletingId === entry.id ? "Deleting..." : "Delete"}
                        </Button>
                      </TableCell>
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
