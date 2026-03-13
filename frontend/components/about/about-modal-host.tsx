"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";

import { AboutContent } from "@/components/about/about-content";
import { consumePendingAboutModal, OPEN_ABOUT_MODAL_EVENT } from "@/lib/about-modal";

export function AboutModalHost() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const onOpen = () => {
      consumePendingAboutModal();
      setOpen(true);
    };
    window.addEventListener(OPEN_ABOUT_MODAL_EVENT, onOpen as EventListener);
    return () => {
      window.removeEventListener(OPEN_ABOUT_MODAL_EVENT, onOpen as EventListener);
    };
  }, []);

  useEffect(() => {
    if (consumePendingAboutModal()) {
      setOpen(true);
    }
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] bg-black/50 p-4"
      role="presentation"
      onClick={() => setOpen(false)}
    >
      <div
        className="mx-auto max-h-[calc(100dvh-2rem)] w-full max-w-3xl overflow-y-auto rounded-xl border border-border bg-background p-5 shadow-xl sm:p-6"
        role="dialog"
        aria-modal="true"
        aria-label="About Us"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close About dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <AboutContent />
      </div>
    </div>
  );
}
