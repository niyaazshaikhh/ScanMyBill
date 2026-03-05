import { promises as fs } from 'fs';
import path from 'path';

import type { MetadataRoute } from 'next';

type SitemapEntry = MetadataRoute.Sitemap[number];
type ChangeFrequency = NonNullable<SitemapEntry['changeFrequency']>;

type RouteSeoHint = {
  changeFrequency: ChangeFrequency;
  priority: number;
};

type DiscoveredRoute = {
  routePath: string;
  lastModified: Date;
};

const PAGE_FILE_NAMES = new Set(['page.tsx', 'page.ts', 'page.jsx', 'page.js', 'page.mdx']);

const PRIVATE_ROUTE_GROUPS = new Set(['(app)', '(auth)']);

const EXCLUDED_ROUTE_PATHS = new Set([
  '/signin',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/admin/signin',
]);

const EXCLUDED_ROUTE_PREFIXES = [
  '/admin',
  '/api',
  '/dashboard',
  '/clients',
  '/create',
  '/invoices',
  '/settings',
  '/newsletter',
  '/hsn-sac-master-list',
  '/client-analytics',
];

const ROUTE_SEO_HINTS = new Map<string, RouteSeoHint>([
  ['/', { changeFrequency: 'daily', priority: 1 }],
  ['/pricing', { changeFrequency: 'weekly', priority: 0.85 }],
  ['/about', { changeFrequency: 'monthly', priority: 0.7 }],
]);

const NOINDEX_PATTERNS = [
  /name\s*=\s*['"]robots['"][^>]*content\s*=\s*['"][^'"]*\bnoindex\b/i,
  /content\s*=\s*['"][^'"]*\bnoindex\b[^'"]*['"][^>]*name\s*=\s*['"]robots['"]/i,
  /robots\s*:\s*\{[\s\S]*?index\s*:\s*false/i,
  /robots\s*:\s*['"]noindex['"]/i,
];

function normalizeSiteUrl(rawUrl: string): string {
  const trimmed = rawUrl.trim();
  if (!trimmed) return 'http://localhost:3000';
  return trimmed.replace(/\/+$/, '');
}

function isRouteGroupSegment(segment: string): boolean {
  return segment.startsWith('(') && segment.endsWith(')');
}

function isDynamicSegment(segment: string): boolean {
  return segment.startsWith('[') && segment.endsWith(']');
}

function routePathFromSegments(segments: string[]): string {
  const urlSegments = segments.filter((segment) => !isRouteGroupSegment(segment));
  if (urlSegments.length === 0) return '/';
  return `/${urlSegments.join('/')}`;
}

function isRouteExcluded(routePath: string): boolean {
  if (EXCLUDED_ROUTE_PATHS.has(routePath)) return true;
  return EXCLUDED_ROUTE_PREFIXES.some(
    (prefix) => routePath === prefix || routePath.startsWith(`${prefix}/`)
  );
}

function resolveSeoHint(routePath: string): RouteSeoHint {
  const directHint = ROUTE_SEO_HINTS.get(routePath);
  if (directHint) return directHint;

  if (routePath.startsWith('/blog')) {
    return { changeFrequency: 'weekly', priority: 0.8 };
  }

  if (routePath.startsWith('/invoice') || routePath.startsWith('/invoices-public')) {
    return { changeFrequency: 'weekly', priority: 0.75 };
  }

  return { changeFrequency: 'monthly', priority: 0.6 };
}

async function listPageFilesRecursively(directory: string): Promise<string[]> {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const pageFiles: string[] = [];

  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const fullPath = path.join(directory, entry.name);

    if (entry.isDirectory()) {
      const nestedFiles = await listPageFilesRecursively(fullPath);
      pageFiles.push(...nestedFiles);
      continue;
    }

    if (entry.isFile() && PAGE_FILE_NAMES.has(entry.name)) {
      pageFiles.push(fullPath);
    }
  }

  return pageFiles;
}

async function fileContainsNoindex(filePath: string): Promise<boolean> {
  try {
    const fileContent = await fs.readFile(filePath, 'utf-8');
    return NOINDEX_PATTERNS.some((pattern) => pattern.test(fileContent));
  } catch {
    return false;
  }
}

async function routeHasNoindex(routeDirectory: string): Promise<boolean> {
  const noindexFileNames = [
    'head.tsx',
    'head.ts',
    'head.jsx',
    'head.js',
    'page.tsx',
    'page.ts',
    'page.jsx',
    'page.js',
    'layout.tsx',
    'layout.ts',
    'layout.jsx',
    'layout.js',
  ];

  for (const fileName of noindexFileNames) {
    const filePath = path.join(routeDirectory, fileName);
    if (await fileContainsNoindex(filePath)) {
      return true;
    }
  }

  return false;
}

async function discoverIndexableRoutes(appDirectory: string): Promise<DiscoveredRoute[]> {
  const pageFiles = await listPageFilesRecursively(appDirectory);
  const discoveredRoutes = new Map<string, Date>();

  for (const pageFile of pageFiles) {
    const relativeFilePath = path.relative(appDirectory, pageFile);
    const routeDirectory = path.dirname(relativeFilePath);
    const routeSegments = routeDirectory === '.' ? [] : routeDirectory.split(path.sep).filter(Boolean);

    if (routeSegments.some((segment) => PRIVATE_ROUTE_GROUPS.has(segment))) {
      continue;
    }

    if (routeSegments.some(isDynamicSegment)) {
      continue;
    }

    const routePath = routePathFromSegments(routeSegments);
    if (isRouteExcluded(routePath)) {
      continue;
    }

    const absoluteRouteDirectory = path.dirname(pageFile);
    if (await routeHasNoindex(absoluteRouteDirectory)) {
      continue;
    }

    const pageStats = await fs.stat(pageFile);
    const existingLastModified = discoveredRoutes.get(routePath);
    if (!existingLastModified || pageStats.mtime > existingLastModified) {
      discoveredRoutes.set(routePath, pageStats.mtime);
    }
  }

  return Array.from(discoveredRoutes.entries())
    .map(([routePath, lastModified]) => ({ routePath, lastModified }))
    .sort((a, b) => {
      if (a.routePath === '/') return -1;
      if (b.routePath === '/') return 1;
      return a.routePath.localeCompare(b.routePath);
    });
}

function toAbsoluteUrl(siteUrl: string, routePath: string): string {
  if (routePath === '/') return `${siteUrl}/`;
  return `${siteUrl}${routePath}`;
}

export async function generateAutomaticSitemap(): Promise<MetadataRoute.Sitemap> {
  const siteUrl = normalizeSiteUrl(process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000');
  const appDirectory = path.join(process.cwd(), 'app');
  const routes = await discoverIndexableRoutes(appDirectory);

  return routes.map((route): SitemapEntry => {
    const seoHint = resolveSeoHint(route.routePath);
    return {
      url: toAbsoluteUrl(siteUrl, route.routePath),
      lastModified: route.lastModified,
      changeFrequency: seoHint.changeFrequency,
      priority: seoHint.priority,
    };
  });
}

