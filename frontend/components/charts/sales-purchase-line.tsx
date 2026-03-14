'use client';

import { useCallback, useMemo } from 'react';

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
} from 'recharts';
import { formatAccountingAmount, formatAccountingInteger } from '@/lib/number-format';
import { useTheme } from '@/hooks/useTheme';

type TrendPoint = {
  label: string;
  sales: number;
  purchases: number;
};

type PeriodValue = 'monthly' | 'quarterly' | 'semi-annually' | 'annually';

const BAR_SERIES = [
  { key: 'sales', label: 'Sales', color: '#ea580c' },
  { key: 'purchases', label: 'Purchases', color: '#0f766e' },
] as const;

function formatCompactAmount(value: number): string {
  if (!Number.isFinite(value)) return '0';
  const abs = Math.abs(value);

  if (abs >= 1_00_00_000) {
    const amountInCrores = value / 1_00_00_000;
    return `${amountInCrores.toFixed(abs >= 10_00_00_000 ? 0 : 1)}Cr`;
  }

  if (abs >= 1_00_000) {
    const amountInLakhs = value / 1_00_000;
    return `${amountInLakhs.toFixed(abs >= 10_00_000 ? 0 : 1)}L`;
  }

  if (abs >= 1_000) {
    const amountInThousands = value / 1_000;
    return `${amountInThousands.toFixed(abs >= 10_000 ? 0 : 1)}K`;
  }

  return formatAccountingInteger(value);
}

function nextReadableStep(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 1_000;
  const exponent = Math.floor(Math.log10(value));
  const magnitude = 10 ** exponent;
  const normalized = value / magnitude;

  if (normalized <= 1) return 1 * magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function shortMonthFromLabel(label: string): string | null {
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;
  const lower = label.trim().toLowerCase();
  if (!lower) return null;

  const monthIndex = MONTHS.findIndex((month) => lower.includes(month.toLowerCase()));
  if (monthIndex >= 0) return MONTHS[monthIndex];

  const numericMonthMatch = lower.match(/\b(0?[1-9]|1[0-2])\b/);
  if (numericMonthMatch) {
    return MONTHS[Number(numericMonthMatch[1]) - 1];
  }

  const parsedDate = new Date(label);
  if (!Number.isNaN(parsedDate.getTime())) {
    return MONTHS[parsedDate.getMonth()];
  }

  return null;
}

function quarterFromLabel(label: string): string | null {
  const lower = label.trim().toLowerCase();
  const qMatch = lower.match(/q\s*([1-4])/i);
  if (qMatch) return `Q${qMatch[1]}`;

  const quarterMatch = lower.match(/quarter\s*([1-4])/i);
  if (quarterMatch) return `Q${quarterMatch[1]}`;

  return null;
}

function yearFromLabel(label: string): string | null {
  const trimmed = label.trim();
  const fyMatch = trimmed.match(/FY\s*\d{2,4}[-/]\d{2,4}/i);
  if (fyMatch) return fyMatch[0].toUpperCase();

  const yearMatch = trimmed.match(/\b(20\d{2}|19\d{2})\b/);
  if (yearMatch) return yearMatch[1];

  const parsedDate = new Date(trimmed);
  if (!Number.isNaN(parsedDate.getTime())) {
    return String(parsedDate.getFullYear());
  }

  return null;
}

function resolveXAxisLabel(label: string, period: PeriodValue, index: number): string {
  if (period === 'monthly') {
    return shortMonthFromLabel(label) || label || `M${index + 1}`;
  }
  if (period === 'quarterly') {
    return quarterFromLabel(label) || `Q${index + 1}`;
  }
  if (period === 'semi-annually') {
    const lower = label.trim().toLowerCase();
    if (lower.includes('h1') || lower.includes('first half')) return 'H1';
    if (lower.includes('h2') || lower.includes('second half')) return 'H2';
    return `H${index + 1}`;
  }
  return yearFromLabel(label) || label || `Y${index + 1}`;
}

export function SalesPurchaseBarChart({
  data,
  period,
}: {
  data: TrendPoint[];
  period: PeriodValue;
}) {
  const { currentTheme } = useTheme();
  const isDark = currentTheme === 'dark';

  const chartData = useMemo(() => {
    return data.map((point, index) => ({
      ...point,
      xLabel: resolveXAxisLabel(point.label, period, index),
      originalLabel: point.label,
    }));
  }, [data, period]);

  const yAxisMax = useMemo(() => {
    const maxValue = chartData.reduce((max, point) => {
      return Math.max(max, Number(point.sales || 0), Number(point.purchases || 0));
    }, 0);

    if (maxValue <= 0) return 1_000;
    const withPadding = maxValue * 1.1;
    const step = nextReadableStep(withPadding / 5);
    return Math.ceil(withPadding / step) * step;
  }, [chartData]);

  const renderTooltip = useCallback(
    ({ active, label, payload }: TooltipProps<number | string, string | number>) => {
      if (!active || !payload?.length) return null;

      const firstPayload = payload[0]?.payload;
      const originalLabel =
        typeof firstPayload?.originalLabel === 'string'
          ? firstPayload.originalLabel
          : null;
      const displayLabel =
        originalLabel && originalLabel !== label
          ? `${String(label)} (${originalLabel})`
          : String(label ?? '');

      return (
        <div
          className='min-w-[11rem] rounded-md border px-3 py-2 sm:min-w-[13rem]'
          style={{
            backgroundColor: isDark ? '#1e293b' : '#ffffff',
            borderColor: isDark ? '#334155' : '#e2e8f0',
            color: isDark ? '#f1f5f9' : '#0f172a',
            boxShadow: isDark
              ? '0 12px 24px rgba(2, 6, 23, 0.45)'
              : '0 10px 20px rgba(15, 23, 42, 0.12)',
          }}
        >
          <p
            className='mb-2 text-xs font-semibold tracking-wide'
            style={{ color: isDark ? '#f1f5f9' : '#0f172a' }}
          >
            {displayLabel}
          </p>
          <div className='space-y-1.5'>
            {payload.map((item, index) => {
              const dataKeyValue = typeof item.dataKey === 'string' ? item.dataKey : String(item.dataKey || '');
              const tone =
                item.color ||
                BAR_SERIES.find((series) => series.key === dataKeyValue)?.color ||
                (isDark ? '#cbd5e1' : '#334155');
              const itemLabel =
                typeof item.name === 'string' || typeof item.name === 'number'
                  ? String(item.name)
                  : dataKeyValue === 'sales'
                    ? 'Sales'
                    : dataKeyValue === 'purchases'
                      ? 'Purchases'
                      : 'Amount';
              const numericValue = Number(item.value ?? 0);

              return (
                <div
                  key={`${item.dataKey || itemLabel}-${index}`}
                  className='flex items-center justify-between gap-3'
                >
                  <span
                    className='flex items-center gap-2 text-xs font-medium sm:text-sm'
                    style={{ color: isDark ? '#cbd5e1' : '#334155' }}
                  >
                    <span
                      className='inline-block h-2.5 w-2.5 rounded-full'
                      style={{ backgroundColor: tone }}
                      aria-hidden='true'
                    />
                    {itemLabel}
                  </span>
                  <span
                    className='text-xs font-semibold tabular-nums sm:text-sm'
                    style={{ color: tone }}
                  >
                    Rs {formatAccountingAmount(numericValue)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      );
    },
    [isDark],
  );

  return (
    <div className='w-full space-y-3'>
      <div className='flex flex-wrap items-center gap-3 px-1'>
        {BAR_SERIES.map((series) => (
          <div key={series.key} className='flex items-center gap-2 text-xs font-medium text-muted-foreground sm:text-sm'>
            <span
              className='inline-block h-2.5 w-2.5 rounded-full'
              style={{ backgroundColor: series.color }}
              aria-hidden='true'
            />
            <span>{series.label}</span>
          </div>
        ))}
      </div>
      <div className='h-72 w-full sm:h-80'>
        <ResponsiveContainer width='100%' height='100%'>
          <BarChart data={chartData} barCategoryGap='24%' barGap={8}>
            <CartesianGrid strokeDasharray='3 3' stroke={isDark ? '#334155' : '#e7dcca'} />
            <XAxis
              dataKey='xLabel'
              tick={{ fill: isDark ? '#cbd5e1' : '#475569' }}
              axisLine={{ stroke: isDark ? '#475569' : '#cbd5e1' }}
              tickLine={{ stroke: isDark ? '#475569' : '#cbd5e1' }}
            />
            <YAxis
              width={74}
              domain={[0, yAxisMax]}
              tickCount={6}
              tick={{ fill: isDark ? '#cbd5e1' : '#475569' }}
              axisLine={{ stroke: isDark ? '#475569' : '#cbd5e1' }}
              tickLine={{ stroke: isDark ? '#475569' : '#cbd5e1' }}
              tickFormatter={(value) => formatCompactAmount(Number(value))}
            />
            <Tooltip
              content={renderTooltip}
              cursor={{ fill: isDark ? 'rgba(148, 163, 184, 0.16)' : 'rgba(15, 23, 42, 0.06)' }}
              allowEscapeViewBox={{ x: true, y: true }}
              wrapperStyle={{ zIndex: 30, outline: 'none', pointerEvents: 'none' }}
            />
            <Bar dataKey='sales' fill='#ea580c' radius={[6, 6, 0, 0]} activeBar={{ fill: '#ea580c' }} />
            <Bar dataKey='purchases' fill='#0f766e' radius={[6, 6, 0, 0]} activeBar={{ fill: '#0f766e' }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export { SalesPurchaseBarChart as SalesPurchaseLineChart };
