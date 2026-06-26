-- Execution layer: content-addressable cache index + per-stage execution journal.
-- Forward-only, additive. Existing tables are untouched, so old jobs keep working.
-- Run in the Supabase SQL editor or via the migration runner.

-- ────────────────────────────────────────────────────────────────────────────
-- cache_entries
--   Backs core/cache: one row per content-addressable artifact.
--   `value` holds small JSON results (probe/transcript/LLM); `blob_ref` points
--   into the BlobStore (CAS) for large media. The key IS the deterministic
--   artifact id, so this table also serves the idempotency "skip if exists" check.
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.cache_entries (
  key         text primary key,             -- sha256(operation | version | inputs)
  operation   text not null,                -- e.g. "whisper", "llm_score", "clip_extract"
  version     integer not null,             -- per-operation stage_version (bump to invalidate)
  kind        text not null check (kind in ('json', 'blob')),
  value       jsonb,                         -- json kind: inline result
  blob_ref    text,                          -- blob kind: opaque CAS ref
  ext         text,
  size        bigint not null default 0,
  hit_count   bigint not null default 0,
  created_at  timestamptz not null default now(),
  accessed_at timestamptz not null default now(),
  expires_at  timestamptz                    -- null = permanent (content-addressed)
);

create index if not exists cache_entries_operation on public.cache_entries (operation);
create index if not exists cache_entries_expires   on public.cache_entries (expires_at);

-- Infra table: never reachable via the anon key. Enable RLS with no policies so
-- only the service-role worker client (which bypasses RLS) can touch it.
alter table public.cache_entries enable row level security;

-- ────────────────────────────────────────────────────────────────────────────
-- job_stages
--   The execution journal + per-stage checkpoints + artifact registry view.
--   One row per (job, pipeline stage). On resume, the runner reads these rows
--   and skips stages whose status='complete' and whose input_fingerprint still
--   matches and whose output artifacts still exist.
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.job_stages (
  id                 uuid primary key default gen_random_uuid(),
  job_id             uuid not null references public.clip_jobs(job_id) on delete cascade,
  stage              text not null,          -- node name: analyze_video, clipping_logic, ...
  status             text not null default 'pending'
                       check (status in ('pending', 'running', 'complete', 'failed')),
  input_fingerprint  text,                   -- hash of the stage's resolved inputs+config
  output_artifact_ids jsonb,                 -- cache keys / paths this stage produced
  attempt            integer not null default 1,
  error              text,
  started_at         timestamptz,
  completed_at       timestamptz,
  updated_at         timestamptz not null default now(),
  unique (job_id, stage)
);

create index if not exists job_stages_job on public.job_stages (job_id);

create or replace trigger job_stages_updated_at
  before update on public.job_stages
  for each row execute function public.set_updated_at();

-- Owners may read their own job's stage journal (for a future stage-detail UI);
-- writes are service-role only (workers), so no insert/update policies are added.
alter table public.job_stages enable row level security;

create policy "job_stages_select_owner" on public.job_stages
  for select using (
    exists (
      select 1 from public.clip_jobs j
      where j.job_id = job_stages.job_id and j.user_id = auth.uid()
    )
  );
