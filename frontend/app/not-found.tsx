import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

export default function NotFound() {
  return (
    <main className='relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-12'>
      <div className='pointer-events-none absolute inset-0'>
        <div className='absolute -left-20 -top-24 h-64 w-64 rounded-full bg-orange-300/30 blur-3xl' />
        <div className='absolute -bottom-20 -right-16 h-72 w-72 rounded-full bg-teal-300/30 blur-3xl' />
      </div>

      <Card className='hero-grid relative w-full max-w-2xl border-orange-300/70 bg-white/85 shadow-xl backdrop-blur'>
        <CardContent className='space-y-6 p-8 text-center sm:p-10'>
          <p className='inline-flex rounded-full border border-orange-300 bg-orange-50 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-orange-700'>
            Error 404
          </p>

          <div className='space-y-3'>
            <h1 className='font-[var(--font-space)] text-4xl font-semibold tracking-tight text-foreground sm:text-5xl'>
              This Page Could Not Be Found
            </h1>
            <p className='mx-auto max-w-xl text-sm text-muted-foreground sm:text-base'>
              The link may be broken or the page may have been moved. You can return to the homepage
              or continue to your dashboard.
            </p>
          </div>

          <div className='flex flex-col justify-center gap-3 sm:flex-row'>
            <Button asChild size='lg'>
              <Link href='/'>Go To Home</Link>
            </Button>
            <Button asChild size='lg' variant='outline'>
              <Link href='/dashboard'>Open Dashboard</Link>
            </Button>
          </div>

          <p className='text-xs text-muted-foreground'>
            Need help?{' '}
            <a className='text-primary hover:underline' href='mailto:support@scanmybill.xyz'>
              support@scanmybill.xyz
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

