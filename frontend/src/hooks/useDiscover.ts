"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobStore } from "@/store/jobStore";
import type { DiscoverRequest } from "@/types/api";

/**
 * Curated topic keys for the discovery chips. Loaded once and cached —
 * the bank rarely changes.
 */
export function useDiscoverTopics() {
  return useQuery({
    queryKey: ["discover-topics"],
    queryFn: () => api.getDiscoverTopics(),
    staleTime: 1000 * 60 * 60, // 1h
  });
}

/**
 * On-demand trending-video search. Results are per-search, not polled —
 * a mutation fits better than a query here.
 */
export function useDiscover() {
  const { addToast } = useJobStore();

  return useMutation({
    mutationFn: (body: DiscoverRequest) => api.discover(body),
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}
