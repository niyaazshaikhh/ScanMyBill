import type { MetadataRoute } from 'next';

import { generateAutomaticSitemap } from '@/lib/seo/sitemap';

export const revalidate = 3600;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  return generateAutomaticSitemap();
}
