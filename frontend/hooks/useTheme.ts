'use client';

import { useThemeContext } from '@/components/theme-provider';

export function useTheme() {
  const { currentTheme, toggleTheme } = useThemeContext();
  return { currentTheme, toggleTheme };
}
