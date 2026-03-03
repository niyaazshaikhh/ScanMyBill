const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

function financialYearLabelFromIsoDate(isoDate: string): string {
  const match = ISO_DATE_PATTERN.exec(isoDate.trim());
  if (!match) return "0000-00";

  const year = Number(match[1]);
  const month = Number(match[2]);
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
    return "0000-00";
  }

  const startYear = month >= 4 ? year : year - 1;
  const endYearTwoDigits = String((startYear + 1) % 100).padStart(2, "0");
  return `${startYear}-${endYearTwoDigits}`;
}

function extractDocumentNumber(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "0";

  const maybeSuffix = trimmed.includes("/") ? (trimmed.split("/").pop() || "").trim() : trimmed;
  const sanitized = maybeSuffix.replace(/[^A-Za-z0-9_-]/g, "");
  return sanitized || "0";
}

function sanitizeClientName(value: string | null | undefined): string {
  const source = (value || "").trim();
  if (!source) return "Client";

  const sanitized = source.replace(/[^A-Za-z0-9_-]/g, "");
  return sanitized || "Client";
}

export function buildBillPdfFilename(params: {
  billDateIso: string;
  documentNumber: string;
  clientName: string | null | undefined;
}): string {
  const yearLabel = financialYearLabelFromIsoDate(params.billDateIso);
  const number = extractDocumentNumber(params.documentNumber);
  const client = sanitizeClientName(params.clientName);
  return `${yearLabel}_${number}-${client}.pdf`;
}

