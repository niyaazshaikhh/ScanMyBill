const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

export function todayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = pad2(now.getMonth() + 1);
  const day = pad2(now.getDate());
  return `${year}-${month}-${day}`;
}

export function formatIsoDateToDisplay(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate.trim());
  if (!match) return '';
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  const day = Number(match[3]);
  if (!Number.isInteger(year) || monthIndex < 0 || monthIndex > 11 || day < 1 || day > 31) return '';
  return `${pad2(day)}/${MONTHS[monthIndex]}/${year}`;
}

export function parseDisplayDateToIso(displayDate: string): string | null {
  const match = /^(\d{2})\/([A-Za-z]{3})\/(\d{4})$/.exec(displayDate.trim());
  if (!match) return null;

  const day = Number(match[1]);
  const monthToken = `${match[2][0].toUpperCase()}${match[2].slice(1).toLowerCase()}`;
  const monthIndex = MONTHS.findIndex((month) => month === monthToken);
  const year = Number(match[3]);
  if (!Number.isInteger(day) || !Number.isInteger(year) || monthIndex < 0) return null;

  const date = new Date(year, monthIndex, day);
  if (
    date.getFullYear() !== year
    || date.getMonth() !== monthIndex
    || date.getDate() !== day
  ) {
    return null;
  }

  return `${year}-${pad2(monthIndex + 1)}-${pad2(day)}`;
}

export function isoYear(isoDate: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate.trim());
  if (!match) return new Date().getFullYear();
  return Number(match[1]);
}

export function isoMonthIndex(isoDate: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate.trim());
  if (!match) return 0;
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) return 0;
  return monthIndex;
}

