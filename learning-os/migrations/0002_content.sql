-- 0002_content.sql — Content Ingestion's raw content store (immutable evidence).
-- One row per (owner, normalized-URL hash) → re-remembering the same link is idempotent.

CREATE TABLE IF NOT EXISTS content (
    content_id    uuid PRIMARY KEY,
    owner_id      uuid        NOT NULL,
    source_type   text        NOT NULL
                  CHECK (source_type IN ('youtube', 'youtube_shorts', 'article', 'documentation')),
    url           text        NOT NULL,
    content_hash  text        NOT NULL,
    title         text,
    status        text        NOT NULL DEFAULT 'saved'
                  CHECK (status IN ('saved', 'ingesting', 'ingested', 'failed')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, content_hash)
);

CREATE INDEX IF NOT EXISTS content_owner_created_idx ON content (owner_id, created_at DESC);

-- Tenant isolation: services connect as a service role and always filter by owner_id in SQL
-- (the gateway derives owner_id from the verified JWT). Enable RLS here if this DB is exposed
-- directly to end users:
--   ALTER TABLE content ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY content_owner_select ON content FOR SELECT USING (owner_id = auth.uid());
