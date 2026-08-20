# ADR 0001: Durable modular monolith with SQL and Redis

- Status: accepted
- Date: 2026-08-21

## Context

The original single-process game stored rooms and raw player identifiers in memory. Restarts lost games, multiple instances diverged, and process locks could not enforce cross-instance resolution or idempotency.

## Decision

Keep the tested rules in `backend/game.py` and place an application-service boundary around them. PostgreSQL stores the authoritative room snapshot plus normalized sessions, rounds, actions, results, idempotency records, and events. Mutations acquire a room row lock and commit as one SQL transaction. Redis provides disposable TTL markers, distributed rate limits, and room-version pub/sub. WebSocket messages are regenerated per authenticated viewer from committed SQL state.

Local development uses async SQLite and in-process implementations of Redis-facing ports. Production requires migrations and PostgreSQL; Redis is strongly recommended and included in the supported Compose topology.

## Consequences

- Restarts and horizontal scaling preserve games and identity continuity.
- The existing engine remains readable and independently testable.
- SQL is the source of truth; Redis outages affect coordination/performance, not stored outcomes.
- The snapshot/normalized hybrid duplicates some data, requiring transactional synchronization and invariants.
- Production operation now requires database migration, backup, Redis, and observability practices.
