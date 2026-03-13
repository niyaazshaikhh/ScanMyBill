import { Instagram, Linkedin, Twitter } from "lucide-react";

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

export function AboutContent() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-[var(--font-space)] text-2xl font-semibold sm:text-3xl">
          About Us
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          ScanMyBill is built specially for Indian MSMEs to simplify invoice
          management and GST workflows.
        </p>
      </div>

      <div className="rounded-xl border border-orange-200 bg-card/85 p-5 dark:border-slate-700">
        <h3 className="font-[var(--font-space)] text-xl font-semibold">
          Developer
        </h3>
        <p className="mt-4 text-base">
          <span className="font-semibold">Niyaz Shaikh</span>
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Building practical SaaS tools focused on AI-powered automation,
          billing operations, and compliance workflows.
        </p>

        <div className="mt-4 flex flex-wrap gap-3">
          {socialLinks.map((link) => {
            const Icon = link.icon;
            return (
              <a
                key={link.name}
                className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm font-medium text-primary hover:bg-muted"
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
      </div>
    </div>
  );
}
