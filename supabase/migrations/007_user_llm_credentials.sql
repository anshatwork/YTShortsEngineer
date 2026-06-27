-- BYOK (bring-your-own-key) LLM credentials: one row per user.
-- The API key is stored ENCRYPTED (Fernet, see tools/llm/byok.py) — never raw.
-- Run in the Supabase SQL editor (or via supabase db push). Depends on
-- 001_jobs.sql (set_updated_at() trigger function).

create table if not exists public.user_llm_credentials (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  provider     text not null check (provider in ('claude')),
  api_key_enc  text not null,           -- Fernet ciphertext; never the raw key
  model        text,                    -- optional model override (e.g. claude-…)
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create or replace trigger user_llm_credentials_updated_at
  before update on public.user_llm_credentials
  for each row execute function public.set_updated_at();

-- Row Level Security: NO user-facing policy. The encrypted key is read and
-- written exclusively by the FastAPI worker using the service-role key. The UI
-- gets non-secret status (provider/model) via the API, never by querying this
-- table directly — so a leaked anon key cannot reach even the ciphertext.
alter table public.user_llm_credentials enable row level security;
