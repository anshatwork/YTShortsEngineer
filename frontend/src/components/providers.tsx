"use client";

import { useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  QueryCache,
  MutationCache,
} from "@tanstack/react-query";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { pushDebug } from "@/lib/debugLog";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        // Capture every query/mutation failure centrally so they land in the
        // debug buffer ("Copy debug logs"), not just in ad-hoc toasts.
        queryCache: new QueryCache({
          onError: (error, query) => {
            pushDebug("error", "query", `query failed: ${query.queryHash}`, error);
          },
        }),
        mutationCache: new MutationCache({
          onError: (error, _vars, _ctx, mutation) => {
            const key = mutation.options.mutationKey ?? "(unkeyed)";
            pushDebug("error", "mutation", `mutation failed: ${JSON.stringify(key)}`, error);
          },
        }),
        defaultOptions: {
          queries: {
            retry: 2,
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
