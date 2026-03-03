const INVOICE_NUMBER_PATTERN = /^\d{4}-\d{2}\/\d{3}$/;
const DESCRIPTION_PATTERN = /^[A-Za-z0-9 ]+$/;
const HSN_SAC_PATTERN = /^\d{4,15}$/;
const NUMBER_WITH_TWO_DECIMALS_PATTERN = /^\d+(\.\d{1,2})?$/;

export const MAX_QUANTITY = 5_000_000;

function hasMaxTwoDecimals(value: number): boolean {
  return Math.round(value * 100) === value * 100;
}

export function formatFinancialYearInvoicePrefix(dateValue: string): string {
  const parsedDate = new Date(dateValue);
  const year = Number.isNaN(parsedDate.getTime()) ? new Date() : parsedDate;
  const financialYearStart = year.getMonth() >= 3 ? year.getFullYear() : year.getFullYear() - 1;
  const financialYearEndShort = String((financialYearStart + 1) % 100).padStart(2, '0');
  return `${financialYearStart}-${financialYearEndShort}`;
}

export function buildDefaultInvoiceNumber(dateValue: string): string {
  return `${formatFinancialYearInvoicePrefix(dateValue)}/001`;
}

export function buildIncrementedInvoiceNumber(
  dateValue: string,
  latestInvoiceNumber?: string | null,
): string {
  const prefix = formatFinancialYearInvoicePrefix(dateValue);
  const candidate = (latestInvoiceNumber || '').trim();
  if (!INVOICE_NUMBER_PATTERN.test(candidate)) {
    return `${prefix}/001`;
  }

  const previousSerial = Number(candidate.slice(8));
  if (!Number.isFinite(previousSerial) || previousSerial <= 0 || previousSerial > 999) {
    return `${prefix}/001`;
  }

  const nextSerial = previousSerial >= 999 ? 1 : previousSerial + 1;
  return `${prefix}/${String(nextSerial).padStart(3, '0')}`;
}

export function sanitizeInvoiceNumberInput(value: string): string {
  return value.toUpperCase().replace(/[^0-9/-]/g, '').slice(0, 11);
}

export function validateInvoiceNumber(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Invoice Number is required.';
  if (!INVOICE_NUMBER_PATTERN.test(trimmed)) {
    return 'Invoice Number should be in format YYYY-YY/NNN.';
  }

  const startYear = Number(trimmed.slice(0, 4));
  const nextYearShort = Number(trimmed.slice(5, 7));
  const expectedNextYearShort = (startYear + 1) % 100;
  if (nextYearShort !== expectedNextYearShort) {
    return 'Invoice Number year segment is invalid. Expected YYYY-(YYYY+1)/NNN format.';
  }
  return null;
}

export function sanitizeItemDescriptionInput(value: string): string {
  return value.replace(/[^A-Za-z0-9 ]/g, '').slice(0, 20);
}

export function validateItemDescription(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Description is required.';
  if (!DESCRIPTION_PATTERN.test(trimmed)) {
    return 'Description should be alphanumeric and special characters are not allowed.';
  }
  return null;
}

export function sanitizeHsnSacInput(value: string): string {
  return value.replace(/\D/g, '').slice(0, 15);
}

export function validateHsnSac(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'HSN/SAC is required.';
  if (!HSN_SAC_PATTERN.test(trimmed)) return 'HSN/SAC should contain 4 to 15 digits.';
  return null;
}

export function sanitizeDecimalInput(value: string): string {
  const sanitized = value.replace(/[^0-9.]/g, '');
  const [whole = '', fraction = ''] = sanitized.split('.');
  if (!sanitized.includes('.')) return whole;
  return `${whole}.${fraction.slice(0, 2)}`;
}

export function validateQuantity(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Quantity is required.';
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric) || numeric <= 0) return 'Quantity should be a valid number greater than 0.';
  if (numeric > MAX_QUANTITY) return 'Quantity should be up to 50,00,000.';
  return null;
}

export function validateRate(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Rate is required.';
  if (!NUMBER_WITH_TWO_DECIMALS_PATTERN.test(trimmed)) {
    return 'Rate should be a number with up to 2 decimal places.';
  }
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric) || numeric < 0) return 'Rate should be a valid non-negative number.';
  if (!hasMaxTwoDecimals(numeric)) return 'Rate should have up to 2 decimal places.';
  return null;
}

export function validateTaxRate(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Tax Rate is required.';
  if (!NUMBER_WITH_TWO_DECIMALS_PATTERN.test(trimmed)) {
    return 'Tax Rate should be a number with up to 2 decimal places.';
  }
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric) || numeric < 0) return 'Tax Rate should be a valid non-negative number.';
  if (numeric > 99.99) return 'Tax Rate should be up to 99.99%.';
  if (!hasMaxTwoDecimals(numeric)) return 'Tax Rate should have up to 2 decimal places.';
  return null;
}

export function toNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
