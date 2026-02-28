import Link from 'next/link';

import { RazorpayDemoButton } from '@/components/landing/razorpay-demo-button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const metadata = {
  title: 'Pricing'
};

export default function PricingPage() {
  return (
    <main className='mx-auto max-w-4xl px-4 py-14 sm:px-6'>
      <Card className='border-teal-200 bg-white/90'>
        <CardHeader>
          <CardTitle className='font-[var(--font-space)] text-3xl'>Pricing</CardTitle>
        </CardHeader>
        <CardContent className='space-y-4 text-sm'>
          <p>
            Demo setup includes Razorpay subscription flow. Configure your API keys and plan id to enable live test mode checkout.
          </p>
          <RazorpayDemoButton />
          <p>
            Need full billing setup? Continue to{' '}
            <Link href='/signup' className='text-primary'>
              sign up
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </main>
  );
}