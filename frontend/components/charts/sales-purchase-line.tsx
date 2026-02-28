'use client';

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type TrendPoint = {
  label: string;
  sales: number;
  purchases: number;
};

export function SalesPurchaseLineChart({ data }: { data: TrendPoint[] }) {
  return (
    <div className='h-80 w-full'>
      <ResponsiveContainer width='100%' height='100%'>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray='3 3' stroke='#e7dcca' />
          <XAxis dataKey='label' />
          <YAxis />
          <Tooltip />
          <Line type='monotone' dataKey='sales' stroke='#ea580c' strokeWidth={2.5} />
          <Line type='monotone' dataKey='purchases' stroke='#0f766e' strokeWidth={2.5} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}