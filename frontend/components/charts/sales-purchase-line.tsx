'use client';

import { useMemo } from 'react';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { formatAccountingAmount, formatAccountingInteger } from '@/lib/number-format';

type TrendPoint = {
  label: string;
  sales: number;
  purchases: number;
};

const LINE_SERIES = [
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

export function SalesPurchaseLineChart({ data }: { data: TrendPoint[] }) {
  const yAxisMax = useMemo(() => {
    const maxValue = data.reduce((max, point) => {
      return Math.max(max, Number(point.sales || 0), Number(point.purchases || 0));
    }, 0);

    if (maxValue <= 0) return 1_000;
    const withPadding = maxValue * 1.1;
    const step = nextReadableStep(withPadding / 5);
    return Math.ceil(withPadding / step) * step;
  }, [data]);

  return (
    <div className='w-full space-y-3'>
      <div className='flex flex-wrap items-center gap-3 px-1'>
        {LINE_SERIES.map((series) => (
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
          <LineChart data={data}>
            <CartesianGrid strokeDasharray='3 3' stroke='#e7dcca' />
            <XAxis dataKey='label' />
            <YAxis
              width={74}
              domain={[0, yAxisMax]}
              tickCount={6}
              tickFormatter={(value) => formatCompactAmount(Number(value))}
            />
            <Tooltip formatter={(value) => `Rs ${formatAccountingAmount(Number(value))}`} />
            <Line type='monotone' dataKey='sales' stroke='#ea580c' strokeWidth={2.5} />
            <Line type='monotone' dataKey='purchases' stroke='#0f766e' strokeWidth={2.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
