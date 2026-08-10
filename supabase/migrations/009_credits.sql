-- Credit ledger: append-only record of every credit grant / debit / refund. A user's
-- balance is SUM(amount) over the rows (grants are +, debits are -, refunds are +), so
-- there is no mutable balance column to drift out of sync — same philosophy as counting
-- usage directly from clip_jobs (see subscription_store / 008_subscriptions.sql).
--
-- Written exclusively by the FastAPI worker (service-role key): grants come from verified
-- payment webhooks, debits from metered operations. Never written through a user JWT.
-- Run in the Supabase SQL editor (or via supabase db push). Depends on 001_jobs.sql
-- (auth.users) and 008_subscriptions.sql.

create table if not exists public.credit_ledger (
  id               bigint generated always as identity primary key,
  user_id          uuid not null references auth.users(id) on delete cascade,
  amount           integer not null,
  kind             text not null check (kind in ('grant', 'debit', 'refund')),
  reason           text,
  -- Idempotency guard: repeated webhooks (Stripe checkout.session.completed, Razorpay
  -- subscription.charged) must not double-grant. A grant carries a stable key; a NULL key
  -- (debits/refunds) is exempt from the uniqueness check.
  idempotency_key  text,
  period_start     timestamptz not null default now(),
  created_at       timestamptz not null default now()
);

-- Balance is computed per user per period, so index the read path.
create index if not exists credit_ledger_user_period
  on public.credit_ledger (user_id, period_start);

-- Enforce grant idempotency: at most one ledger row per non-null key.
create unique index if not exists credit_ledger_idempotency_key
  on public.credit_ledger (idempotency_key)
  where idempotency_key is not null;

-- Row Level Security: owners may READ their own ledger (the UI shows the balance); all
-- writes happen via the worker, so there is no insert/update/delete policy.
alter table public.credit_ledger enable row level security;

create policy "credit_ledger_select" on public.credit_ledger
  for select using (auth.uid() = user_id);
