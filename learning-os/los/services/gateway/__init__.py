"""API Gateway — the client edge. Verifies the Supabase JWT, derives ``owner_id``, and proxies to
downstream services with a trusted ``X-User-Id`` header. Downstream services never re-verify the JWT;
they trust the gateway-set owner (service-to-service auth is added in a later phase)."""
