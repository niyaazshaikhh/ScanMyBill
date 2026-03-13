'use client';

import { Button } from '@/components/ui/button';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';

export function ThemeToggle({ className }: { className?: string }) {
  const { currentTheme, toggleTheme } = useTheme();
  const isDark = currentTheme === 'dark';

  return (
    <Button
      type='button'
      variant='outline'
      size='icon'
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={cn('relative overflow-hidden text-base', className)}
    >
      <span
        aria-hidden='true'
        className={cn(
          'inline-flex items-center justify-center transition-transform duration-300',
          isDark ? 'rotate-0 scale-100' : 'rotate-90 scale-90'
        )}
      >
        {isDark ? '☀' : '🌙'}
      </span>
    </Button>
  );
}
