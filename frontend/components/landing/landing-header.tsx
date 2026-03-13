"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AboutTrigger } from "@/components/about/about-trigger";
import { ThemeToggle } from "@/components/theme-toggle";
import { InstallAppButton } from "@/components/pwa/install-app-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SECTION_LINKS = [
  { id: "features", label: "Features", href: "#features" },
  { id: "pricing", label: "Pricing", href: "#pricing" },
  { id: "faq", label: "FAQ", href: "#faq" },
  { id: "contact", label: "Contact Us", href: "#contact" },
] as const;

export function LandingHeader() {
  const [activeSection, setActiveSection] = useState<string>("");

  const updateActiveSection = useCallback(() => {
    if (typeof window === "undefined") return;

    const markerPosition = window.scrollY + 140;
    let nextActiveSection = "";

    for (const section of SECTION_LINKS) {
      const node = document.getElementById(section.id);
      if (!node) continue;
      if (markerPosition >= node.offsetTop) {
        nextActiveSection = section.id;
      }
    }

    setActiveSection(nextActiveSection);
  }, []);

  useEffect(() => {
    updateActiveSection();
    window.addEventListener("scroll", updateActiveSection, { passive: true });
    window.addEventListener("resize", updateActiveSection);
    return () => {
      window.removeEventListener("scroll", updateActiveSection);
      window.removeEventListener("resize", updateActiveSection);
    };
  }, [updateActiveSection]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
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
          <AboutTrigger label="About Us" />
          {SECTION_LINKS.map((item) => (
            <a
              key={item.id}
              href={item.href}
              className={cn(
                "relative pb-1 transition-colors duration-300 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:origin-center after:bg-primary after:transition-transform after:duration-300",
                activeSection === item.id
                  ? "text-foreground after:scale-x-100"
                  : "text-muted-foreground after:scale-x-0 hover:text-foreground hover:after:scale-x-100",
              )}
            >
              {item.label}
            </a>
          ))}
          <Button asChild size="sm" variant="outline">
            <Link href="/signin">Log in</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/signup">Sign up</Link>
          </Button>
          <InstallAppButton />
          <ThemeToggle />
        </nav>
        <div className="flex flex-wrap items-center justify-end gap-2 md:hidden">
          <AboutTrigger
            label="About"
            mode="button"
            buttonVariant="ghost"
            buttonSize="sm"
          />
          <Button asChild size="sm" variant="outline">
            <Link href="/signin">Log in</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/signup">Sign up</Link>
          </Button>
          <InstallAppButton />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

