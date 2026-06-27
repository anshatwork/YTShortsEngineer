import { Reveal } from "@/components/landing/Reveal";

// NOTE: lucide-react in this repo ships no brand glyphs, so GitHub/LinkedIn
// marks are inline SVG. Email uses an inline envelope for visual consistency.
// TODO(ansh): replace the GitHub/LinkedIn placeholder URLs with your real ones.
const EMAIL = "ansh.work2002@gmail.com";
const GITHUB_URL = "https://github.com/anshatwork"; // TODO: real handle
const LINKEDIN_URL = "https://www.linkedin.com/in/anshchawla1"; // TODO: real handle

type Channel = {
  label: string;
  value: string;
  href: string;
  external?: boolean;
  icon: React.ReactNode;
};

const MailIcon = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden className="w-5 h-5">
    <rect x="3" y="5" width="18" height="14" rx="1" />
    <path d="m3 7 9 6 9-6" />
  </svg>
);

const GitHubIcon = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className="w-5 h-5">
    <path d="M12 .5A11.5 11.5 0 0 0 .5 12 11.5 11.5 0 0 0 8.34 23c.57.1.78-.25.78-.55v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.04-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.7 1.25 3.36.96.1-.75.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.8 0c2.2-1.5 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.43-2.7 5.4-5.26 5.69.41.36.78 1.07.78 2.16v3.2c0 .31.2.66.79.55A11.5 11.5 0 0 0 23.5 12 11.5 11.5 0 0 0 12 .5Z" />
  </svg>
);

const LinkedInIcon = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className="w-5 h-5">
    <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14ZM7.12 20.45H3.55V9h3.57v11.45ZM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.22.79 24 1.77 24h20.45c.98 0 1.78-.78 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z" />
  </svg>
);

const channels: Channel[] = [
  { label: "Email", value: EMAIL, href: `mailto:${EMAIL}`, icon: MailIcon },
  { label: "GitHub", value: GITHUB_URL.replace(/^https?:\/\//, ""), href: GITHUB_URL, external: true, icon: GitHubIcon },
  { label: "LinkedIn", value: LINKEDIN_URL.replace(/^https?:\/\//, ""), href: LINKEDIN_URL, external: true, icon: LinkedInIcon },
];

export function ContactLinks() {
  return (
    <Reveal delay={0.06}>
      <section className="mt-10">
        <p className="kicker mb-3">Direct lines</p>
        <ul className="border-t border-ink">
          {channels.map((c) => (
            <li key={c.label}>
              <a
                href={c.href}
                {...(c.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                className="group flex items-center gap-4 border-b border-rule-soft py-4 hover:bg-paper-2/60 transition-colors"
              >
                <span className="shrink-0 w-10 h-10 border border-ink flex items-center justify-center text-ink group-hover:bg-ink group-hover:text-paper transition-colors">
                  {c.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft">
                    {c.label}
                  </span>
                  <span className="block text-[15px] text-ink truncate">{c.value}</span>
                </span>
                <span
                  aria-hidden
                  className="font-mono text-ink-soft group-hover:text-ink group-hover:translate-x-0.5 transition-all"
                >
                  ↗
                </span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </Reveal>
  );
}
