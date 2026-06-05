import { LoginButtons } from "@/components/auth/LoginButtons";

export default function LoginPage() {
  return (
    <div className="min-h-[calc(100vh-44px)] flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Header */}
        <div className="space-y-2">
          <p className="font-mono text-[10px] tracking-[0.25em] uppercase text-ink-muted">
            ys · shorts engineer
          </p>
          <h1 className="text-2xl font-serif text-ink leading-tight">
            Sign in to your workspace
          </h1>
          <p className="text-sm text-ink-muted leading-relaxed">
            Jobs are saved to your account and persist across sessions.
          </p>
        </div>

        {/* OAuth buttons — client component */}
        <LoginButtons />

        <p className="font-mono text-[10px] tracking-[0.15em] text-ink-soft text-center">
          By signing in you agree to the terms of service.
        </p>
      </div>
    </div>
  );
}
