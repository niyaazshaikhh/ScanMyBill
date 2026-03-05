import type { Metadata, Viewport } from 'next';
import { Manrope, Space_Grotesk } from 'next/font/google';

import '@/app/globals.css';
import { PWARegister } from '@/components/pwa/pwa-register';
import { CustomCursor } from '@/components/ui/custom-cursor';
import { Providers } from '@/components/providers';

const manrope = Manrope({
  subsets: ['latin'],
  variable: '--font-manrope'
});

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space'
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'),
  applicationName: 'ScanMyBill',
  authors: [{ name: 'Niyaz Shaikh' }],
  creator: 'Niyaz Shaikh',
  manifest: '/manifest.webmanifest',
  icons: {
    icon: [
      { url: '/icon.svg', type: 'image/svg+xml' },
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }
    ],
    shortcut: [{ url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }],
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }]
  },
  title: {
    default: 'ScanMyBill | Smart Bill Management for Indian SMBs',
    template: '%s | ScanMyBill'
  },
  description:
    'Stop manual entries. Start smart bill management with OCR-powered uploads, GST analytics, and invoice exports.',
  alternates: {
    canonical: '/'
  },
  keywords: [
    'bill management',
    'invoice OCR',
    'GST dashboard',
    'SaaS billing software',
    'ScanMyBill'
  ],
  openGraph: {
    title: 'ScanMyBill',
    description: 'Stop Manual Entries. Start Smart Bill Management.',
    url: '/',
    siteName: 'ScanMyBill',
    locale: 'en_IN',
    type: 'website'
  },
  robots: {
    index: true,
    follow: true
  }
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#d4550d'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='en'>
      <body className={`${manrope.variable} ${spaceGrotesk.variable} font-[var(--font-manrope)]`}>
        <Providers>
          <PWARegister />
          <CustomCursor />
          {children}
        </Providers>
      </body>
    </html>
  );
}
