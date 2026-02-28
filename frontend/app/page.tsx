import Link from 'next/link';

import { DraggableBills } from '@/components/landing/draggable-bills';
import { RazorpayDemoButton } from '@/components/landing/razorpay-demo-button';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const features = [
  {
    title: 'OCR-Powered Bill Capture',
    body: 'Upload image/PDF bills and auto-extract date, GSTIN, amount, and bill type.'
  },
  {
    title: 'GST Dashboard Intelligence',
    body: 'Track GST collected, paid, and payable with period-wise analytics and visual trends.'
  },
  {
    title: 'Folder-Based Invoices',
    body: 'Browse monthly/quarterly/semi-annual/yearly folders and export consolidated PDFs.'
  },
  {
    title: 'Client Revenue Insights',
    body: 'See top clients, transactions, and revenue instantly without manual reconciliation.'
  }
];

export default function LandingPage() {
  return (
    <div className='min-h-screen'>
      <header className='sticky top-0 z-50 border-b border-border/60 bg-background/95 backdrop-blur'>
        <div className='mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8'>
          <Link href='/' className='font-[var(--font-space)] text-xl font-bold tracking-tight text-primary'>
            ScanMyBill.in
          </Link>
          <nav className='hidden items-center gap-5 text-sm font-medium md:flex'>
            <Link href='/signin'>Sign In</Link>
            <Link href='/signup'>Sign Up</Link>
            <a href='#about'>About Us</a>
            <a href='#pricing'>Pricing</a>
            <a href='#contact'>Contact Us</a>
            <Button asChild size='sm' variant='outline'>
              <Link href='/signin?provider=google'>Google Sign-In</Link>
            </Button>
          </nav>
          <Button asChild size='sm' className='md:hidden'>
            <Link href='/signin'>Sign In</Link>
          </Button>
        </div>
      </header>

      <main>
        <section className='mx-auto grid w-full max-w-7xl gap-8 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-2 lg:px-8 lg:pt-16'>
          <div className='fade-up space-y-6'>
            <p className='inline-flex rounded-full bg-secondary px-3 py-1 text-xs font-semibold uppercase tracking-wide text-secondary-foreground'>
              SaaS for Smart GST Teams
            </p>
            <h1 className='font-[var(--font-space)] text-4xl font-semibold leading-tight text-foreground sm:text-5xl'>
              Stop Manual Entries. Start Smart Bill Management.
            </h1>
            <p className='max-w-xl text-lg text-muted-foreground'>
              ScanMyBill.in helps Indian businesses process bills faster with OCR, track GST exposure,
              and export grouped invoices in one click.
            </p>
            <div className='flex flex-col gap-3 sm:flex-row'>
              <Button asChild size='lg'>
                <Link href='/signup'>Start Free Trial</Link>
              </Button>
              <Button asChild size='lg' variant='outline'>
                <Link href='/dashboard'>Open Demo Dashboard</Link>
              </Button>
            </div>
          </div>
          <div className='fade-up'>
            <DraggableBills />
          </div>
        </section>

        <section id='about' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8'>
          <div className='mb-6 flex items-end justify-between'>
            <h2 className='font-[var(--font-space)] text-3xl font-semibold'>Key Features</h2>
            <Link href='/signup' className='text-sm font-semibold text-primary'>
              Create Account
            </Link>
          </div>
          <div className='grid gap-4 md:grid-cols-2'>
            {features.map((feature) => (
              <Card key={feature.title} className='border-orange-200/70 bg-white/75'>
                <CardContent className='space-y-2 p-5'>
                  <h3 className='font-semibold'>{feature.title}</h3>
                  <p className='text-sm text-muted-foreground'>{feature.body}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section id='pricing' className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8'>
          <Card className='border-teal-200 bg-teal-50/70'>
            <CardContent className='grid gap-6 p-6 md:grid-cols-[1fr_auto] md:items-center'>
              <div>
                <h3 className='font-[var(--font-space)] text-2xl font-semibold'>Pricing and Payments</h3>
                <p className='mt-2 text-sm text-muted-foreground'>
                  Run a Razorpay subscription checkout with test credentials to validate your billing flow.
                </p>
              </div>
              <RazorpayDemoButton />
            </CardContent>
          </Card>
        </section>

        <section className='mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8'>
          <Card className='border-amber-300 bg-amber-100/70'>
            <CardContent className='space-y-3 p-6'>
              <h3 className='font-[var(--font-space)] text-2xl font-semibold'>Newsletter Signup</h3>
              <p className='text-sm text-muted-foreground'>
                Get product updates on OCR, GST compliance, and automation workflows.
              </p>
              <form className='flex flex-col gap-3 sm:flex-row'>
                <input
                  type='email'
                  required
                  placeholder='you@company.com'
                  className='h-10 w-full rounded-md border border-border bg-white px-3 text-sm sm:max-w-sm'
                />
                <Button type='submit'>Subscribe</Button>
              </form>
            </CardContent>
          </Card>
        </section>
      </main>

      <footer id='contact' className='border-t border-border/70 bg-white/80'>
        <div className='mx-auto grid w-full max-w-7xl gap-6 px-4 py-8 text-sm sm:px-6 md:grid-cols-4 lg:px-8'>
          <div>
            <h4 className='font-semibold'>Contact</h4>
            <p className='mt-2 text-muted-foreground'>support@scanmybill.in</p>
            <p className='mt-1 text-muted-foreground'>
              Personal: <a className='text-primary' href='mailto:neyazshaikh777@gmail.com'>neyazshaikh777@gmail.com</a>
            </p>
            <p className='mt-1 text-muted-foreground'>Built by Niyaz Shaikh</p>
            <div className='mt-2 flex flex-wrap gap-3 text-xs'>
              <a
                className='text-primary hover:underline'
                href='https://x.com/niyaazshaikhh'
                target='_blank'
                rel='noreferrer'
              >
                X
              </a>
              <a
                className='text-primary hover:underline'
                href='https://www.linkedin.com/in/niyaazshaikhh/'
                target='_blank'
                rel='noreferrer'
              >
                LinkedIn
              </a>
              <a
                className='text-primary hover:underline'
                href='https://www.instagram.com/whyniyaaz/'
                target='_blank'
                rel='noreferrer'
              >
                Instagram
              </a>
            </div>
          </div>
          <div>
            <h4 className='font-semibold'>Terms</h4>
            <p className='mt-2 text-muted-foreground'>Standard SaaS terms available on signup.</p>
          </div>
          <div>
            <h4 className='font-semibold'>Privacy</h4>
            <p className='mt-2 text-muted-foreground'>Data encrypted in transit and role-protected.</p>
          </div>
          <div>
            <h4 className='font-semibold'>FAQ</h4>
            <p className='mt-2 text-muted-foreground'>OCR accuracy, exports, and GST analytics support.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
