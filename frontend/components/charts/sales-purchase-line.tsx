'use client';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { formatAccountingAmount } from '@/lib/number-format';

type TrendPoint = {
  label: string;
  sales: number;
  purchases: number;
};

const LINE_SERIES = [
  { key: 'sales', label: 'Sales', color: '#ea580c' },
  { key: 'purchases', label: 'Purchases', color: '#0f766e' },
] as const;

export function SalesPurchaseLineChart({ data }: { data: TrendPoint[] }) {
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
            <YAxis tickFormatter={(value) => formatAccountingAmount(Number(value))} />
            <Tooltip formatter={(value) => `Rs ${formatAccountingAmount(Number(value))}`} />
            <Line type='monotone' dataKey='sales' stroke='#ea580c' strokeWidth={2.5} />
            <Line type='monotone' dataKey='purchases' stroke='#0f766e' strokeWidth={2.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
