"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import { useJobStore } from "@/store/jobStore";

/**
 * Re-run a failed (or any) job with its original parameters. The backend
 * creates a NEW job from the stored request and enqueues it; we then navigate
 * to the new job's detail page, mirroring useSubmitJob.
 */
export function useRerunJob() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const { user } = useAuth();
  const { setActiveJob, addToast } = useJobStore();

  return useMutation({
    mutationKey: ["rerunJob"],
    mutationFn: (jobId: string) => api.rerunJob(jobId),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["jobs", user?.id ?? null] });
      setActiveJob(job.job_id);
      addToast("Job re-running…", "info");
      router.push(`/jobs/${job.job_id}`);
    },
    onError: (err: Error) => {
      addToast(err.message, "error");
    },
  });
}
