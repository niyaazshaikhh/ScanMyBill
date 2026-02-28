import type { Metadata } from 'next';
import { Manrope, Space_Grotesk } from 'next/font/google';

import '@/app/globals.css';
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
  title: {
    default: 'ScanMyBill.in | Smart Bill Management for Indian SMBs',
    template: '%s | ScanMyBill.in'
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
    'ScanMyBill.in'
  ],
  openGraph: {
    title: 'ScanMyBill.in',
    description: 'Stop Manual Entries. Start Smart Bill Management.',
    url: '/',
    siteName: 'ScanMyBill.in',
    locale: 'en_IN',
    type: 'website'
  },
  robots: {
    index: true,
    follow: true
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang='en'>
      <body className={`${manrope.variable} ${spaceGrotesk.variable} font-[var(--font-manrope)]`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}