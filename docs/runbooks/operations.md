# Operations runbook

## Readiness failure

1. Check `docker compose ps` and `docker compose logs --tail=200 app postgres redis`.
2. Inspect `/api/ready`; its dependency map identifies database, cache, or event-bus failure.
3. For database failures, verify connectivity, credentials, capacity, and `alembic current` versus `alembic heads`.
4. For Redis failures, restore Redis connectivity. Existing SQL state remains authoritative; connected clients recover through HTTP polling.
5. Do not route traffic until readiness is green.

## Migration failure

1. Keep app replicas stopped or on the compatible previous version.
2. Read `docker compose logs migrate`; do not repeatedly retry a partially applied non-transactional migration.
3. Compare schema state with `docker compose run --rm migrate alembic current`.
4. Restore the pre-deploy backup or execute the reviewed downgrade, depending on the migration’s documented recovery plan.
5. Correct the migration in a new commit; never edit an already deployed revision in place.

## Elevated errors or latency

1. Correlate JSON logs by `request_id`, `room_code`, and `trace_id`.
2. Check PostgreSQL lock waits/connections, Redis latency, CPU, memory, and event-loop saturation.
3. A surge of `CONCURRENT_MUTATION` indicates retries or lock contention; confirm clients use stable idempotency keys.
4. A surge of `RATE_LIMIT_EXCEEDED` can be abusive traffic or overly strict configuration. Preserve limits while identifying the source.
5. Scale app replicas only after database and Redis capacity are healthy.

## Room appears stale

1. Fetch the viewer-specific HTTP state; it is authoritative over a missed WebSocket notification.
2. Check Redis pub/sub health and app logs for the room code.
3. Confirm all replicas use the same Redis URL/key prefix and PostgreSQL database.
4. Reconnect the client socket. Do not manually mutate Redis to repair game state.

## Backup restore

1. Stop writes and take a final backup if possible.
2. Restore PostgreSQL into an isolated database and run integrity/smoke checks.
3. Point a staging app at the restored database with the matching code/schema version.
4. Validate room reads, session authentication, and a complete game flow.
5. Promote using the platform’s controlled database cutover procedure.
