"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import type { DiscoverSuggestionsResponse } from "@/types/api";

/**
 * Personalized trending suggestions, polled in the background so the navbar
 * badge stays fresh. Gated on a signed-in user (pattern from useJob).
 */
export function useDiscoverSuggestions() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<DiscoverSuggestionsResponse>({
    queryKey: ["discover-suggestions", userId],
    queryFn: () => api.getDiscoverSuggestions(),
    enabled: userId !== null,
    refetchInterval: 120_000,
    staleTime: 60_000,
  });
}

/**
 * Mark suggestions as seen (clears the unread badge). On success we invalidate
 * the suggestions query so new_count refreshes to 0.
 */
export function useMarkSuggestionsSeen() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useMutation({
    mutationFn: () => api.markSuggestionsSeen(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["discover-suggestions", userId] });
    },
  });
}
