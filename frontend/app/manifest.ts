import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'ScanMyBill',
    short_name: 'ScanMyBill',
    description: 'AI-powered bill management and GST workflow platform specially made for Indian MSMEs.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: '#fff8f1',
    theme_color: '#d4550d',
    orientation: 'portrait',
    icons: [
      {
        src: '/icons/icon-192.png',
        sizes: '192x192',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'any',
      },
      {
        src: '/icons/icon-512-maskable.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
