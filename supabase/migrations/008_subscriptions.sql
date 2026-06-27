-- Subscription / plan state: one row per paying user. Absence of a row means the
-- user is on the free plan. Written exclusively by the FastAPI worker from
-- verified payment webhooks (service-role key) — never through a user JWT.
-- Run in the Supabase SQL editor (or via supabase db push). Depends on
-- 001_jobs.sql (set_updated_at() trigger function).

create table if not exists public.subscriptions (
  user_id                  uuid primary key references auth.users(id) on delete cascade,
  plan                     text not null default 'free'
                             check (plan in ('free', 'pro', 'business')),
  status                   text not null default 'active'
                             check (status in ('active', 'trialing', 'past_due', 'canceled')),
  provider                 text check (provider in ('stripe', 'razorpay')),
  provider_customer_id     text,
  provider_subscription_id text,
  current_period_end       timestamptz,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

-- Look up an active subscription by the provider's subscription id (webhook path).
create index if not exists subscriptions_provider_sub
  on public.subscriptions (provider, provider_subscription_id);

create or replace trigger subscriptions_updated_at
  before update on public.subscriptions
  for each row execute function public.set_updated_at();

-- Row Level Security: owners may READ their own plan (the UI shows it); all
-- writes happen via the worker from signed webhooks, so no insert/update policy.
alter table public.subscriptions enable row level security;

create policy "subscriptions_select" on public.subscriptions
  for select using (auth.uid() = user_id);
