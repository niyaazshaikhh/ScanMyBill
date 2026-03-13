'use client';

import { GoogleOAuthProvider } from '@react-oauth/google';

import { ThemeProvider } from '@/components/theme-provider';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ''}>
        {children}
      </GoogleOAuthProvider>
    </ThemeProvider>
  );
}
