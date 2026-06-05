"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { ShellStatus } from "./ShellStatus";
import { YouTubeConnect } from "./YouTubeConnect";
import { useAuth } from "@/components/auth/AuthProvider";

const navLinks = [
  { href: "/", label: "WORKSPACE" },
  { href: "/new", label: "NEW JOB" },
];

/**
 * Compact 44px sticky shell — wordmark on the left, nav segments centred,
 * live status counter and user avatar on the right.
 */
export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut, isLoading, isLocalDev } = useAuth();

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

        {/* Live status — hidden on small screens */}
        <div className="hidden md:block">
          <ShellStatus />
        </div>

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
