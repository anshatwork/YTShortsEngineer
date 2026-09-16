-- 0001_event_store.sql — the durable event log + transactional outbox.
-- This is the genuinely new primitive the Learning OS adds on top of the parent repo's EventBus:
-- an append-only, replayable source of truth for domain events. The outbox decouples the DB commit
-- from the broker publish (no lost/duplicate events across a crash).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS domain_events (
    event_id        uuid PRIMARY KEY,
    stream          text        NOT NULL,          -- e.g. 'content-<uuid>'
    seq             bigint      NOT NULL,           -- per-stream monotonic sequence
    type            text        NOT NULL,           -- e.g. 'ContentSaved'
    version         int         NOT NULL DEFAULT 1, -- envelope schema version (replay/evolution)
    owner_id        uuid        NOT NULL,           -- tenant scope (every event is owned)
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    correlation_id  uuid,                            -- per user-action trace
    causation_id    uuid,                            -- parent event
    payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (stream, seq)                             -- guards concurrent appends to one stream
);

CREATE INDEX IF NOT EXISTS domain_events_type_idx        ON domain_events (type);
CREATE INDEX IF NOT EXISTS domain_events_owner_idx       ON domain_events (owner_id);
CREATE INDEX IF NOT EXISTS domain_events_occurred_idx    ON domain_events (occurred_at);
CREATE INDEX IF NOT EXISTS domain_events_type_seq_idx    ON domain_events (type, occurred_at, seq); -- replay-by-type

-- Transactional outbox: one row per appended event, drained to the broker by the relay.
CREATE TABLE IF NOT EXISTS outbox (
    event_id      uuid PRIMARY KEY REFERENCES domain_events (event_id) ON DELETE CASCADE,
    published     boolean     NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz
);

-- Partial index: the relay only ever scans unpublished rows.
CREATE INDEX IF NOT EXISTS outbox_unpublished_idx ON outbox (created_at) WHERE published = false;
