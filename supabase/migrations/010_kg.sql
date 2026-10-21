-- Knowledge-graph ingestion registry.
--
-- The semantic graph itself lives in Neo4j (see core/kg). Supabase remains the
-- system-of-record for OWNERSHIP and INGESTION JOB tracking: `assets` records who
-- owns each uploaded/produced media asset and its content hash (the cross-store
-- anchor: assets.content_hash == the Neo4j MediaAsset stable key), and
-- `ingestion_jobs` tracks each run of the agents/ingestion sub-graph so the API can
-- expose status/SSE exactly like clip_jobs.
--
-- Written by the FastAPI worker (service-role key, bypasses RLS). Owners may READ
-- their own rows via RLS. Run in the Supabase SQL editor / `supabase db push`.
-- Depends on 001_jobs.sql (auth.users + public.set_updated_at()).

-- ---------------------------------------------------------------------------
-- assets — one row per owned media asset (video, image, doc, ...)
-- ---------------------------------------------------------------------------
create table if not exists public.assets (
  asset_id      uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  media_type    text not null check (
                  media_type in ('video','image','screenshot','document','slide','audio')),
  uri           text not null,                 -- source path / URL / upload id
  filename      text,                          -- original display name
  title         text,
  content_hash  text,                          -- sha256; anchors the Neo4j MediaAsset
  status        text not null default 'registered' check (
                  status in ('registered','ingesting','ingested','failed')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists assets_user on public.assets (user_id, created_at desc);
-- One logical asset per (user, content_hash): re-registering the same bytes is a
-- no-op upsert target, which keeps ingestion idempotent across uploads.
create unique index if not exists assets_user_content_hash
  on public.assets (user_id, content_hash)
  where content_hash is not null;

drop trigger if exists set_assets_updated_at on public.assets;
create trigger set_assets_updated_at
  before update on public.assets
  for each row execute function public.set_updated_at();

alter table public.assets enable row level security;
create policy "assets_select" on public.assets
  for select using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- ingestion_jobs — one row per run of the ingestion sub-graph
-- ---------------------------------------------------------------------------
create table if not exists public.ingestion_jobs (
  ingestion_job_id uuid primary key default gen_random_uuid(),
  asset_id         uuid not null references public.assets(asset_id) on delete cascade,
  user_id          uuid not null references auth.users(id) on delete cascade,
  status           text not null default 'queued' check (
                     status in ('queued','running','done','failed')),
  current_node     text,
  error            text,
  stats            jsonb,          -- {"nodes": n, "edges": m, "entities": k, ...}
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists ingestion_jobs_user on public.ingestion_jobs (user_id, created_at desc);
create index if not exists ingestion_jobs_asset on public.ingestion_jobs (asset_id);

drop trigger if exists set_ingestion_jobs_updated_at on public.ingestion_jobs;
create trigger set_ingestion_jobs_updated_at
  before update on public.ingestion_jobs
  for each row execute function public.set_updated_at();

alter table public.ingestion_jobs enable row level security;
create policy "ingestion_jobs_select" on public.ingestion_jobs
  for select using (auth.uid() = user_id);
