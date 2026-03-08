import type { Metadata } from "next";
import Link from "next/link";
import { Instagram, Linkedin, Twitter } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "About Us",
  description:
    "Know the developer behind ScanMyBill, the AI billing platform specially made for Indian MSMEs.",
};

const socialLinks = [
  {
    name: "X",
    href: "https://x.com/niyaazshaikhh",
    icon: Twitter,
  },
  {
    name: "LinkedIn",
    href: "https://www.linkedin.com/in/niyaazshaikhh/",
    icon: Linkedin,
  },
  {
    name: "Instagram",
    href: "https://www.instagram.com/whyniyaaz/",
    icon: Instagram,
  },
];

export default function AboutPage() {
  return (
    <main className="mx-auto min-h-screen w-full max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="font-[var(--font-space)] text-3xl font-semibold">
            About Us
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            ScanMyBill is built specially for Indian MSMEs to simplify invoice
            management and GST workflows.
          </p>
        </div>
        <Link href="/" className="text-sm font-medium text-primary">
          &lt; Back to Home
        </Link>
      </div>

      <Card className="border-orange-200 bg-white/85">
        <CardHeader>
          <CardTitle className="font-[var(--font-space)] text-2xl">
            Developer
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-base">
            <span className="font-semibold">Niyaz Shaikh</span>
          </p>
          <p className="text-sm text-muted-foreground">
            Building practical SaaS tools focused on AI-powered automation,
            billing operations, and compliance workflows.
          </p>

          <div className="flex flex-wrap gap-3">
            {socialLinks.map((link) => {
              const Icon = link.icon;
              return (
                <a
                  key={link.name}
                  className="inline-flex items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm font-medium text-primary hover:bg-muted"
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Icon className="h-4 w-4" />
                  {link.name}
                </a>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
