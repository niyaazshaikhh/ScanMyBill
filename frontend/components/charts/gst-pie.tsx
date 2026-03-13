'use client';

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { formatAccountingAmount } from '@/lib/number-format';
import { useTheme } from '@/hooks/useTheme';

type GstPoint = {
  name: string;
  value: number;
};

const COLORS = ['#f97316', '#0d9488', '#be123c'];

export function GstPieChart({ data }: { data: GstPoint[] }) {
  const { currentTheme } = useTheme();
  const isDark = currentTheme === 'dark';
  const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0);

  return (
    <div className='w-full space-y-3'>
      <div className='h-72 w-full sm:h-80'>
        <ResponsiveContainer width='100%' height='100%'>
          <PieChart>
            <Pie
              data={data}
              dataKey='value'
              nameKey='name'
              innerRadius={65}
              outerRadius={110}
              paddingAngle={2}
            >
              {data.map((entry, index) => (
                <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => `Rs ${formatAccountingAmount(Number(value))}`}
              contentStyle={{
                backgroundColor: isDark ? '#1e293b' : '#ffffff',
                borderColor: isDark ? '#334155' : '#e2e8f0',
                color: isDark ? '#f1f5f9' : '#0f172a',
                borderRadius: '0.5rem'
              }}
              labelStyle={{ color: isDark ? '#f1f5f9' : '#0f172a' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className='grid gap-2 sm:grid-cols-2'>
        {data.map((entry, index) => {
          const value = Number(entry.value || 0);
          const percent = total > 0 ? (value / total) * 100 : 0;
          return (
            <div key={entry.name} className='flex items-center justify-between gap-2 rounded-md border border-border bg-background/70 px-2 py-1.5 text-xs sm:text-sm'>
              <div className='flex items-center gap-2'>
                <span
                  className='inline-block h-2.5 w-2.5 rounded-full'
                  style={{ backgroundColor: COLORS[index % COLORS.length] }}
                  aria-hidden='true'
                />
                <span className='font-medium'>{entry.name}</span>
              </div>
              <div className='text-right text-muted-foreground'>
                <span>{percent.toFixed(1)}%</span>
                <span className='ml-2'>Rs {formatAccountingAmount(value)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
