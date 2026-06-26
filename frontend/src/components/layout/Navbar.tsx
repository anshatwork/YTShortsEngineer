"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { YouTubeConnect } from "./YouTubeConnect";
import { useAuth } from "@/components/auth/AuthProvider";
import { useDiscoverSuggestions } from "@/hooks/useDiscoverSuggestions";

const navLinks = [
  { href: "/workspace", label: "WORKSPACE" },
  { href: "/discover", label: "DISCOVER" },
  { href: "/new", label: "NEW JOB" },
  { href: "/create", label: "CREATE" },
  { href: "/contact", label: "CONTACT" },
];

/**
 * Compact 44px sticky shell — wordmark on the left, nav segments centred,
 * live status counter and user avatar on the right.
 */
export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut, isLoading, isLocalDev } = useAuth();
  const { data: suggestions } = useDiscoverSuggestions();
  const newSuggestions = suggestions?.new_count ?? 0;

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
    router.refresh();
  };

  return (
    <header className="sticky top-0 z-50 bg-paper border-b border-ink h-11">
      <div className="h-full max-w-[1280px] mx-auto px-4 sm:px-6 flex items-center gap-6">
        {/* Wordmark */}
        <Link
          href="/"
          className="group flex items-baseline gap-2 shrink-0"
          aria-label="YT Shorts Engineer"
        >
          <span className="script text-[26px] leading-none text-ink translate-y-[1px] group-hover:text-ink-muted transition-colors">
            ys
          </span>
          <span className="font-mono text-[11px] tracking-[0.18em] text-ink-muted hidden sm:inline">
            SHORTS&nbsp;ENGINEER
          </span>
        </Link>

        {/* Nav segments */}
        <nav className="flex items-center gap-1">
          {navLinks.map(({ href, label }) => {
            const active =
              pathname === href ||
              (href !== "/" && pathname.startsWith(href));
            const showBadge = href === "/discover" && newSuggestions > 0;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative px-3 h-11 flex items-center font-mono text-[11px] tracking-[0.18em] transition-colors",
                  active ? "text-ink" : "text-ink-soft hover:text-ink",
                )}
              >
                {label}
                {showBadge && (
                  <span
                    aria-label={`${newSuggestions} new suggestions`}
                    className="absolute top-1.5 right-0 min-w-[15px] h-[15px] px-1 inline-flex items-center justify-center rounded-full bg-[var(--color-mark)] text-paper font-mono text-[9px] font-bold leading-none"
                  >
                    {newSuggestions > 9 ? "9+" : newSuggestions}
                  </span>
                )}
                {active && (
                  <span
                    aria-hidden
                    className="absolute inset-x-3 bottom-0 h-[2px] bg-ink"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Auth controls */}
        {!isLoading && (
          <div className="flex items-center gap-3 shrink-0">
            {(isLocalDev || user) && <YouTubeConnect />}
            {isLocalDev ? (
              <span
                className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-muted"
                title="Supabase not configured — running with AUTH_DISABLED"
              >
                LOCAL · DEV
              </span>
            ) : user ? (
              <>
                {/* User avatar / email */}
                <span
                  className="hidden sm:flex items-center gap-2 font-mono text-[10px] tracking-[0.15em] text-ink-muted"
                  title={user.email}
                >
                  <span
                    aria-hidden
                    className="w-5 h-5 rounded-full bg-ink text-paper flex items-center justify-center text-[9px] font-bold uppercase select-none"
                  >
                    {(user.email?.[0] ?? "U").toUpperCase()}
                  </span>
                  <span className="max-w-[120px] truncate hidden lg:inline">
                    {user.email}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft hover:text-ink transition-colors"
                >
                  SIGN OUT
                </button>
              </>
            ) : (
              <Link
                href="/login"
                className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft hover:text-ink transition-colors"
              >
                SIGN IN
              </Link>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
