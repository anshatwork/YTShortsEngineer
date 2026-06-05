"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";
import type { JobRequest } from "@/types/api";

export function useSubmitJob() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const { user } = useAuth();
  const { setActiveJob, addToast } = useJobStore();

  return useMutation({
    mutationFn: (body: JobRequest) => api.submitJob(body),
    onSuccess: (job) => {
      // Invalidate the user-scoped jobs list
      queryClient.invalidateQueries({ queryKey: ["jobs", user?.id ?? null] });
      setActiveJob(job.job_id);
      router.push(`/jobs/${job.job_id}`);
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}
