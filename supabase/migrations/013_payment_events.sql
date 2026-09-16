-- Durable webhook idempotency. Provider event ids are immutable and unique.
create table if not exists public.payment_events (
  provider text not null check (provider in ('stripe', 'razorpay')),
  event_id text not null,
  received_at timestamptz not null default now(),
  primary key (provider, event_id)
);

alter table public.payment_events enable row level security;
