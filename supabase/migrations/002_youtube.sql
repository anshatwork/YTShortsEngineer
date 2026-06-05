-- YouTube direct-upload schema: stored OAuth credentials + upload job tracking.
-- Run in Supabase SQL editor (or via supabase db push). Depends on 001_jobs.sql
-- (clip_jobs table + set_updated_at() trigger function).

-- ────────────────────────────────────────────────────────────────────────────
-- youtube_credentials  (one row per user — their connected YouTube account)
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.youtube_credentials (
  user_id        uuid primary key references auth.users(id) on delete cascade,
  refresh_token  text not null,           -- long-lived; used to mint access tokens
  access_token   text,                    -- short-lived cache (refreshed as needed)
  token_expiry   timestamptz,             -- when access_token expires
  channel_id     text,
  channel_title  text,
  scopes         text,                    -- space-separated granted scopes
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create or replace trigger youtube_credentials_updated_at
  before update on public.youtube_credentials
  for each row execute function public.set_updated_at();

-- ────────────────────────────────────────────────────────────────────────────
-- youtube_uploads  (tracks async publish jobs — mirrors edit_jobs shape)
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.youtube_uploads (
  upload_id      uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  parent_job_id  uuid references public.clip_jobs(job_id) on delete cascade,
  clip_id        text,
  status         text not null default 'queued'
                   check (status in ('queued', 'running', 'done', 'failed')),
  video_id       text,                    -- YouTube video id (on success)
  video_url      text,                    -- https://youtube.com/watch?v=<id>
  title          text,
  privacy_status text,
  error          text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists youtube_uploads_user_created
  on public.youtube_uploads (user_id, created_at desc);
create index if not exists youtube_uploads_parent
  on public.youtube_uploads (parent_job_id);
create index if not exists youtube_uploads_status
  on public.youtube_uploads (status);

create or replace trigger youtube_uploads_updated_at
  before update on public.youtube_uploads
  for each row execute function public.set_updated_at();

-- ────────────────────────────────────────────────────────────────────────────
-- Row Level Security
-- ────────────────────────────────────────────────────────────────────────────
-- Owners may read their own rows. ALL writes happen via the FastAPI worker
-- using the service-role key (bypasses RLS) — credentials and tokens are never
-- written through a user JWT, so no insert/update policies are granted here.
alter table public.youtube_credentials enable row level security;
alter table public.youtube_uploads      enable row level security;

create policy "youtube_credentials_select" on public.youtube_credentials
  for select using (auth.uid() = user_id);

create policy "youtube_uploads_select" on public.youtube_uploads
  for select using (auth.uid() = user_id);
