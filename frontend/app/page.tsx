import type { Metadata } from "next";
import Link from "next/link";
import {
  BarChart3,
  FileSearch2,
  FolderOpen,
  Instagram,
  Linkedin,
  TrendingUp,
  Twitter,
  type LucideIcon,
} from "lucide-react";

import { DraggableBills } from "@/components/landing/draggable-bills";
import { NewsletterForm } from "@/components/landing/newsletter-form";
import { RazorpayCheckoutButton } from "@/components/landing/razorpay-checkout-button";
import { InstallAppButton } from "@/components/pwa/install-app-button";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Home",
  description:
    "OCR-powered billing and GST workflow platform for Indian businesses. Create invoices, track analytics, and export PDFs quickly.",
};

const features: Array<{
  title: string;
  body: string;
  icon: LucideIcon;
}> = [
  {
    title: "OCR-Powered Bill Capture",
    body: "Upload image/PDF bills and auto-extract date, GSTIN, amount, and bill type.",
    icon: FileSearch2,
  },
  {
    title: "GST Dashboard Intelligence",
    body: "Track GST collected, paid, and payable with period-wise analytics and visual trends.",
    icon: BarChart3,
  },
  {
    title: "Folder-Based Invoices",
    body: "Browse monthly/quarterly/semi-annual/yearly folders and export consolidated PDFs.",
    icon: FolderOpen,
  },
  {
    title: "Client Revenue Insights",
    body: "See top clients, transactions, and revenue instantly without manual reconciliation.",
    icon: TrendingUp,
  },
];

const faqs = [
  {
    question: "How does ScanMyBill pricing work?",
    answer:
      "Pricing is subscription-based through Razorpay. You can start checkout from this page and billing will follow your selected plan cycle.",
  },
  {
    question: "Can I cancel my subscription anytime?",
    answer:
      "Yes. You can cancel before your next billing cycle to stop future charges. Your existing paid period remains active until it ends.",
  },
  {
    question: "Is invoice data secure?",
    answer:
      "We use encrypted transport, access-controlled accounts, and audit-ready data handling practices for business invoices and GST-related records.",
  },
  {
    question: "Do I need technical setup to upload bills?",
    answer:
      "No. You can upload PDFs or images directly, and OCR extraction will map key invoice fields for faster bookkeeping.",
  },
];

const pricingHighlights = [
  {
    name: "Standard",
    price: "Rs 1 / month",
    description: "Good for one person who wants simple bill and tax tracking.",
    accent: "border-slate-200 bg-white",
    points: [
      "Use Dashboard, Invoices, and Settings",
      "Upload bills and keep records in one place",
    ],
  },
  {
    name: "Pro",
    price: "Rs 101 / month",
    description:
      "Best for small teams that want better reports and faster daily work.",
    accent: "border-orange-300 bg-orange-50/40",
    points: [
      "Everything in Standard plan",
      "Includes Client Analytics",
      "Better visibility on client performance",
      "Helpful for teams handling more clients",
    ],
  },
  {
    name: "Business",
    price: "Rs 1001 / month",
    description: "Best for busy businesses that need every section of the app.",
    accent: "border-teal-300 bg-teal-50/40",
    points: [
      "Access to all main routes",
      "Best for full billing workflow",
      "Built for high daily bill volume",
      "Create and manage bills faster with less manual work",
      "Suitable for teams needing complete control",
      "Ideal for growing businesses with regular billing load",
    ],
  },
];

export default function LandingPage() {
  const currentYear = new Date().getFullYear();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md bg-primary font-[var(--font-space)] text-sm font-bold text-primary-foreground">
              SMB
            </span>
            <span className="font-[var(--font-space)] text-xl font-bold tracking-tight text-primary">
              ScanMyBill
            </span>
          </Link>
          <nav className="hidden items-center gap-5 text-sm font-medium md:flex">
            <Link href="/about">About Us</Link>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
            <a href="#contact">Contact Us</a>
            <Button asChild size="sm" variant="outline">
              <Link href="/signin">Log in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/signup">Sign up</Link>
            </Button>
            <InstallAppButton />
          </nav>
          <div className="flex flex-wrap items-center justify-end gap-2 md:hidden">
            <Button asChild size="sm" variant="ghost">
              <Link href="/about">About</Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link href="/signin">Log in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/signup">Sign up</Link>
            </Button>
            <InstallAppButton />
          </div>
        </div>
      </header>

      <main>
        <section className="mx-auto grid w-full max-w-7xl gap-8 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-2 lg:px-8 lg:pt-16">
          <div className="fade-up space-y-6">
            <p className="inline-flex rounded-full bg-secondary px-3 py-1 text-xs font-semibold uppercase tracking-wide text-secondary-foreground">
              SaaS for Smart GST Teams
            </p>
            <h1 className="font-[var(--font-space)] text-4xl font-semibold leading-tight text-foreground sm:text-5xl">
              Stop Manual Entries. Start Smart Bill Management.
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              ScanMyBill helps Indian businesses process bills faster with OCR,
              track GST exposure, and export grouped invoices in one click.
            </p>
            <Button asChild size="lg" className="w-full sm:max-w-md">
              <Link href="/signup">Sign up</Link>
            </Button>
          </div>
          <div className="fade-up">
            <DraggableBills />
          </div>
        </section>

        <section
          id="features"
          className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8"
        >
          <div className="mb-6 flex items-end justify-between">
            <h2 className="font-[var(--font-space)] text-3xl font-semibold">
              Key Features
            </h2>
            <Link href="/signup" className="text-sm font-semibold text-primary">
              Create Account
            </Link>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {features.map((feature) => (
              <Card
                key={feature.title}
                className="border-orange-200/70 bg-white/75"
              >
                <CardContent className="space-y-2 p-5">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                      <feature.icon className="h-4 w-4" />
                    </span>
                    <h3 className="font-semibold">{feature.title}</h3>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {feature.body}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section
          id="pricing"
          className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8"
        >
          <Card className="border-teal-200 bg-teal-50/70">
            <CardContent className="space-y-6 p-6">
              <div>
                <h3 className="font-[var(--font-space)] text-2xl font-semibold">
                  Pricing and Payments
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Activate a secure Razorpay subscription checkout for your
                  ScanMyBill plan.
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Monthly plan with GST invoicing support, OCR processing,
                  dashboard analytics, and invoice exports.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {pricingHighlights.map((plan) => (
                  <div
                    key={plan.name}
                    className={`rounded-xl border p-4 ${plan.accent} min-h-[280px]`}
                  >
                    <p className="font-[var(--font-space)] text-lg font-semibold">
                      {plan.name}
                    </p>
                    <p className="mt-1 text-base font-semibold text-primary">
                      {plan.price}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {plan.description}
                    </p>
                    <ul className="mt-3 space-y-1.5">
                      {plan.points.map((point) => (
                        <li
                          key={`${plan.name}-${point}`}
                          className="flex items-start gap-2 text-xs text-muted-foreground"
                        >
                          <span className="mt-0.5 text-emerald-600">✓</span>
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <Link
                  href="/pricing"
                  className="text-sm font-semibold text-primary"
                >
                  View full pricing options
                </Link>
                <RazorpayCheckoutButton className="w-full sm:w-auto" />
              </div>
            </CardContent>
          </Card>
        </section>

        <section
          id="faq"
          className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8"
        >
          <Card className="border-sky-200 bg-sky-50/60">
            <CardContent className="space-y-4 p-6">
              <h3 className="font-[var(--font-space)] text-2xl font-semibold">
                Frequently Asked Questions
              </h3>
              <div className="space-y-3">
                {faqs.map((faq) => (
                  <details
                    key={faq.question}
                    className="group rounded-md border border-sky-200 bg-white/80"
                  >
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">
                      {faq.question}
                      <span className="text-base text-muted-foreground transition group-open:rotate-180">
                        ⌄
                      </span>
                    </summary>
                    <p className="px-4 pb-4 text-sm text-muted-foreground">
                      {faq.answer}
                    </p>
                  </details>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <Card className="border-amber-300 bg-amber-100/70">
            <CardContent className="space-y-3 p-6">
              <h3 className="font-[var(--font-space)] text-2xl font-semibold">
                Newsletter Signup
              </h3>
              <p className="text-sm text-muted-foreground">
                Get product updates on OCR, GST compliance, and automation
                workflows.
              </p>
              <NewsletterForm />
            </CardContent>
          </Card>
        </section>
      </main>

      <footer id="contact" className="border-t border-border/70 bg-white/80">
        <div className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-8 text-sm sm:px-6 md:grid-cols-3 lg:px-8">
          <div>
            <h4 className="font-semibold">Contact</h4>
            <p className="mt-2 text-muted-foreground">
              <a className="text-primary" href="mailto:support@scanmybill.xyz">
                support@scanmybill.xyz
              </a>
            </p>
            <p className="mt-1 text-muted-foreground">
              Personal:{" "}
              <a
                className="text-primary"
                href="mailto:neyazshaikh777@gmail.com"
              >
                neyazshaikh777@gmail.com
              </a>
            </p>
            <p className="mt-1 text-muted-foreground">Built by NIYAZ SHAIKH</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <a
                className="inline-flex items-center gap-2 rounded-md border border-border bg-white px-3 py-1.5 text-xs font-medium text-primary hover:bg-muted"
                href="https://x.com/niyaazshaikhh"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Twitter className="h-3.5 w-3.5" />X
              </a>
              <a
                className="inline-flex items-center gap-2 rounded-md border border-border bg-white px-3 py-1.5 text-xs font-medium text-primary hover:bg-muted"
                href="https://www.linkedin.com/in/niyaazshaikhh/"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Linkedin className="h-3.5 w-3.5" />
                LinkedIn
              </a>
              <a
                className="inline-flex items-center gap-2 rounded-md border border-border bg-white px-3 py-1.5 text-xs font-medium text-primary hover:bg-muted"
                href="https://www.instagram.com/whyniyaaz/"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Instagram className="h-3.5 w-3.5" />
                Instagram
              </a>
            </div>
          </div>
          <div>
            <h4 className="font-semibold">Terms & Conditions</h4>
            <p className="mt-2 text-muted-foreground">
              By using ScanMyBill, you agree to subscription billing, fair usage
              limits, and acceptable use rules. Subscriptions auto-renew until
              canceled before the next billing date.
            </p>
          </div>
          <div>
            <h4 className="font-semibold">Privacy</h4>
            <p className="mt-2 text-muted-foreground">
              We process account, billing, and invoice data only to operate the
              service. Data is encrypted in transit, access-controlled, and
              never sold to third parties.
            </p>
          </div>
        </div>
        <div className="border-t border-border/70">
          <div className="mx-auto flex w-full max-w-7xl flex-col items-start gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary font-[var(--font-space)] text-xs font-bold text-primary-foreground">
              SMB
            </span>
            <p className="text-xs text-muted-foreground">
              © {currentYear} ScanMyBill All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
