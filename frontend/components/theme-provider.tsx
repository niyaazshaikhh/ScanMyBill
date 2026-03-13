'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import {
  applyThemeToDocument,
  DEFAULT_THEME,
  resolveStoredTheme,
  THEME_STORAGE_KEY,
  type Theme
} from '@/lib/theme';

type ThemeContextValue = {
  currentTheme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [currentTheme, setCurrentTheme] = useState<Theme>(DEFAULT_THEME);

  useEffect(() => {
    const storedTheme = resolveStoredTheme(localStorage.getItem(THEME_STORAGE_KEY));
    setCurrentTheme(storedTheme);
    applyThemeToDocument(storedTheme);
    document.documentElement.classList.add('theme-transition-enabled');
  }, []);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      const nextTheme = resolveStoredTheme(event.newValue);
      setCurrentTheme(nextTheme);
      applyThemeToDocument(nextTheme);
    };

    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  const setTheme = useCallback((theme: Theme) => {
    setCurrentTheme(theme);
    applyThemeToDocument(theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(currentTheme === 'dark' ? 'light' : 'dark');
  }, [currentTheme, setTheme]);

  const value = useMemo(
    () => ({
      currentTheme,
      toggleTheme,
      setTheme
    }),
    [currentTheme, setTheme, toggleTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeContext() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useThemeContext must be used within ThemeProvider');
  }
  return context;
}
