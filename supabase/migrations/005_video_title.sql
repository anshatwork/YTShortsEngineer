-- Add a human-readable name to clip_jobs.
-- Run in Supabase SQL editor (or via supabase db push).

alter table public.clip_jobs
  add column if not exists video_title text;
