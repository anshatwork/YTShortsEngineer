"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import type { UsageResponse } from "@/types/api";

/**
 * Current plan, monthly job-cap usage, and credit balance (GET /usage), polled
 * in the background so the navbar meter stays fresh. Gated on a signed-in user
 * (pattern from useDiscoverSuggestions).
 */
export function useUsage() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<UsageResponse>({
    queryKey: ["usage", userId],
    queryFn: () => api.getUsage(),
    enabled: userId !== null,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
