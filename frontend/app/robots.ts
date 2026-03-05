import type { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  const base = (process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000').replace(/\/+$/, '');

  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [
          '/api/',
          '/admin',
          '/dashboard',
          '/signin',
          '/signup',
          '/forgot-password',
          '/reset-password',
          '/clients',
          '/create',
          '/invoices',
          '/settings',
          '/newsletter',
          '/hsn-sac-master-list',
          '/client-analytics',
        ],
      },
    ],
    sitemap: `${base}/sitemap.xml`
  };
}
