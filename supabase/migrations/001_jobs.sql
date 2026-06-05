-- Long-to-Shorts job persistence schema
-- Run in Supabase SQL editor (or via supabase db push).

-- ────────────────────────────────────────────────────────────────────────────
-- clip_jobs
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.clip_jobs (
  job_id       uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  status       text not null default 'queued'
                 check (status in ('queued', 'running', 'done', 'failed')),
  request      jsonb not null,          -- full JobRequest snapshot
  clips        jsonb,                   -- ClipResult[] on completion
  error        text,
  current_node text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- Indexes for the two main read patterns
create index if not exists clip_jobs_user_created
  on public.clip_jobs (user_id, created_at desc);
create index if not exists clip_jobs_status
  on public.clip_jobs (status);

-- Auto-update updated_at on any row change
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create or replace trigger clip_jobs_updated_at
  before update on public.clip_jobs
  for each row execute function public.set_updated_at();

-- ────────────────────────────────────────────────────────────────────────────
-- edit_jobs
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.edit_jobs (
  edit_job_id  uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  operation    text not null check (operation in ('tts', 'music', 'split_screen')),
  parent_job_id uuid references public.clip_jobs(job_id) on delete cascade,
  clip_id      text,
  status       text not null default 'queued'
                 check (status in ('queued', 'running', 'done', 'failed')),
  output_path  text,
  output_url   text,
  error        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists edit_jobs_user_created
  on public.edit_jobs (user_id, created_at desc);
create index if not exists edit_jobs_parent
  on public.edit_jobs (parent_job_id);
create index if not exists edit_jobs_status
  on public.edit_jobs (status);

create or replace trigger edit_jobs_updated_at
  before update on public.edit_jobs
  for each row execute function public.set_updated_at();

-- ────────────────────────────────────────────────────────────────────────────
-- uploads  (phase 1b — tracks user-supplied files)
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.uploads (
  upload_id  text primary key,          -- uuid + extension, e.g. "abc123.mp3"
  user_id    uuid not null references auth.users(id) on delete cascade,
  path       text not null,
  size       bigint,
  created_at timestamptz not null default now()
);

create index if not exists uploads_user
  on public.uploads (user_id);

-- ────────────────────────────────────────────────────────────────────────────
-- Row Level Security
-- ────────────────────────────────────────────────────────────────────────────
alter table public.clip_jobs enable row level security;
alter table public.edit_jobs enable row level security;
alter table public.uploads    enable row level security;

-- clip_jobs policies (users see only their own rows)
create policy "clip_jobs_select" on public.clip_jobs
  for select using (auth.uid() = user_id);

create policy "clip_jobs_insert" on public.clip_jobs
  for insert with check (auth.uid() = user_id);

-- UPDATE is intentionally allowed for the owner only via user JWT, but the
-- FastAPI worker uses the service-role key (bypasses RLS) for status/clips updates.
create policy "clip_jobs_update_owner" on public.clip_jobs
  for update using (auth.uid() = user_id);

-- edit_jobs policies
create policy "edit_jobs_select" on public.edit_jobs
  for select using (auth.uid() = user_id);

create policy "edit_jobs_insert" on public.edit_jobs
  for insert with check (auth.uid() = user_id);

create policy "edit_jobs_update_owner" on public.edit_jobs
  for update using (auth.uid() = user_id);

-- uploads policies
create policy "uploads_select" on public.uploads
  for select using (auth.uid() = user_id);

create policy "uploads_insert" on public.uploads
  for insert with check (auth.uid() = user_id);
