const integerFormatter = new Intl.NumberFormat('en-IN', {
  maximumFractionDigits: 0,
});

const amountFormatter = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatAccountingInteger(value: number): string {
  if (!Number.isFinite(value)) return '0';
  return integerFormatter.format(value);
}

export function formatAccountingAmount(value: number): string {
  if (!Number.isFinite(value)) return '0.00';
  return amountFormatter.format(value);
}
