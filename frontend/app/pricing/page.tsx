import Link from "next/link";
import { X } from "lucide-react";

import { PricingPlanCards } from "@/components/landing/pricing-plan-cards";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = {
  title: "Pricing",
};

export default function PricingPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-14 sm:px-6">
      <Card className="relative border-teal-200 bg-card/90 dark:border-slate-700">
        <Button
          asChild
          type="button"
          variant="ghost"
          size="icon"
          className="absolute right-3 top-3 h-8 w-8"
          aria-label="Close and go to home"
        >
          <Link href="/">
            <X className="h-4 w-4" />
          </Link>
        </Button>
        <CardHeader>
          <CardTitle className="font-[var(--font-space)] text-3xl">
            Pricing
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p>
            Start your ScanMyBill subscription with secure Razorpay checkout for AI-powered workflows built for Indian MSMEs.
          </p>
          <PricingPlanCards />
          <p>
            Need an account first? Continue to{" "}
            <Link href="/signup" className="text-primary">
              sign up
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </main>
  );
}




