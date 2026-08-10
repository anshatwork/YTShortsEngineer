-- Autonomous Publishing Agent — durable, human-gated workflow state machine.
--
-- One row per publishing run. This table is the SOURCE OF TRUTH for the state
-- machine (see core/execution/lifecycle.py PUB_* + agents/publishing): every
-- transition is a persisted UPDATE, so a crash mid-run loses nothing — the
-- recovery sweep re-enqueues the step for the persisted status. The two
-- WAITING_FOR_* states idle until an approval endpoint fires.
--
-- Written by the FastAPI worker (service-role key, bypasses RLS). Owners may
-- READ their own rows via RLS. Run via the Supabase SQL editor / `supabase db
-- push`. Depends on 001_jobs.sql (auth.users + public.set_updated_at()).

create table if not exists public.publishing_jobs (
  publishing_job_id  uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users(id) on delete cascade,
  status             text not null default 'discovering' check (
                       status in (
                         'discovering','waiting_for_source_approval','generating',
                         'scoring','evaluating','revising','waiting_for_upload_approval',
                         'uploading','complete','failed','cancelled')),
  query              text,
  phase_detail       text,
  request            jsonb,         -- the PublishingStartRequest snapshot (for resume)
  candidates         jsonb,         -- ranked, explained DiscoveryRecommendation[]
  approved_video_url text,
  clip_job_id        uuid references public.clip_jobs(job_id) on delete set null,
  scored_clips       jsonb,         -- ScoreCard[]
  selected_clip      jsonb,         -- ClipResult (the auto-selected best clip)
  eval_report        jsonb,         -- EvalReport
  revision_count     int not null default 0,
  upload_id          uuid,          -- FK-free: youtube_uploads row id
  video_id           text,          -- YouTube id once published
  video_url          text,
  error              text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index if not exists publishing_jobs_user
  on public.publishing_jobs (user_id, created_at desc);
-- The crash-recovery sweep scans for active (non-terminal, non-waiting) runs.
create index if not exists publishing_jobs_status
  on public.publishing_jobs (status);

drop trigger if exists set_publishing_jobs_updated_at on public.publishing_jobs;
create trigger set_publishing_jobs_updated_at
  before update on public.publishing_jobs
  for each row execute function public.set_updated_at();

alter table public.publishing_jobs enable row level security;
create policy "publishing_jobs_select" on public.publishing_jobs
  for select using (auth.uid() = user_id);
