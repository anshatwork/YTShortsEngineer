"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";

interface AuthContextValue {
  user: User | null;
  session: Session | null;
  /** Supabase access token — attach as `Authorization: Bearer <token>` */
  accessToken: string | null;
  isLoading: boolean;
  /** True when Supabase env vars are missing — we're in local dev mode. */
  isLocalDev: boolean;
  signOut: () => Promise<void>;
}

// Must match backend `_DEV_USER_ID` in agents/long_to_shorts/api/auth.py.
const DEV_USER_ID = "00000000-0000-0000-0000-000000000001";

const supabaseConfigured = !!(
  process.env.NEXT_PUBLIC_SUPABASE_URL &&
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

// Stand-in user used when Supabase isn't configured (AUTH_DISABLED dev mode).
// Cast through unknown because we only fill the fields the UI actually reads.
const DEV_USER = {
  id: DEV_USER_ID,
  email: "dev@local",
} as unknown as User;

const AuthContext = createContext<AuthContextValue>({
  user: null,
  session: null,
  accessToken: null,
  isLoading: true,
  isLocalDev: !supabaseConfigured,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(supabaseConfigured);

  useEffect(() => {
    if (!supabaseConfigured) return;
    const supabase = createClient();

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setIsLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      setIsLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = async () => {
    if (!supabaseConfigured) return;
    const supabase = createClient();
    await supabase.auth.signOut();
  };

  const user = supabaseConfigured ? (session?.user ?? null) : DEV_USER;

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        accessToken: session?.access_token ?? null,
        isLoading,
        isLocalDev: !supabaseConfigured,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
