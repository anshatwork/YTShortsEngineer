"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { POLL_INTERVAL_LIST } from "@/lib/constants";

export function useJobs() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery({
    // Scope by userId so that React Query never shares cache between accounts.
    queryKey: ["jobs", userId],
    queryFn: api.listJobs,
    enabled: userId !== null,
    refetchInterval: POLL_INTERVAL_LIST,
    staleTime: 5_000,
  });
}
