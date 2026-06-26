-- Personalized trending-topic crawler + suggestions
-- Run in Supabase SQL editor (or via supabase db push). Depends on 001_jobs.sql
-- (reuses public.set_updated_at()).

-- ────────────────────────────────────────────────────────────────────────────
-- trending_pool  — global pool of currently-trending videos the crawler warms.
-- Non-sensitive, shared across users; written via the service-role key.
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.trending_pool (
  video_id      text primary key,        -- YouTube video id (dedupe key)
  topic         text,                    -- curated topic bucket it was crawled under
  payload       jsonb not null,          -- full DiscoverVideo snapshot
  view_count    bigint,
  published_at  timestamptz,
  discovered_at timestamptz not null default now()  -- when first added to the pool
);

create index if not exists trending_pool_discovered
  on public.trending_pool (discovered_at desc);

-- ────────────────────────────────────────────────────────────────────────────
-- user_suggestion_state  — per-user last_seen marker driving the unread badge.
-- ────────────────────────────────────────────────────────────────────────────
create table if not exists public.user_suggestion_state (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  last_seen_at timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create or replace trigger user_suggestion_state_updated_at
  before update on public.user_suggestion_state
  for each row execute function public.set_updated_at();

-- ────────────────────────────────────────────────────────────────────────────
-- Row Level Security
-- ────────────────────────────────────────────────────────────────────────────
alter table public.trending_pool          enable row level security;
alter table public.user_suggestion_state  enable row level security;

-- trending_pool is global/non-sensitive: any authenticated user may read it.
-- Writes happen through the service-role key, which bypasses RLS.
create policy "trending_pool_select" on public.trending_pool
  for select using (true);

-- user_suggestion_state: each user sees and writes only their own row.
create policy "user_suggestion_state_select" on public.user_suggestion_state
  for select using (auth.uid() = user_id);

create policy "user_suggestion_state_insert" on public.user_suggestion_state
  for insert with check (auth.uid() = user_id);

create policy "user_suggestion_state_update_owner" on public.user_suggestion_state
  for update using (auth.uid() = user_id);
