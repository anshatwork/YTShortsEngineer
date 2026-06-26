import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Supabase OAuth callback handler.
 * Exchanges the ?code= param returned by the OAuth provider for a session,
 * then redirects to the workspace (or an error page on failure).
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/workspace";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`);
}
