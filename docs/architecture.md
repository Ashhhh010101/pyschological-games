# Architecture

The application is a modular monolith: one deployable FastAPI process with explicit domain, application, infrastructure, and transport boundaries.

```text
TypeScript client
  ├── HTTP commands and viewer reads
  └── viewer-authenticated WebSocket
              │
FastAPI transport (backend/server.py)
  ├── validation, stable errors, limits, security headers
  ├── correlation logs, traces, metrics, health/readiness
  └── lifecycle and dependency composition
              │
Application services (backend/application)
  ├── session authentication and idempotency
  ├── transactional command orchestration
  └── committed room-version publication
              │
Game engine (backend/game.py)
  ├── unchanged server-authoritative rules
  ├── hidden state and random resolution
  └── viewer-specific projections
              │
Repository interfaces (backend/domain/repositories.py)
       ┌──────┴────────┐
SQLAlchemy/PostgreSQL  Redis
rooms, players,        TTL markers, distributed
rounds, actions,       room locks, rate limits,
snapshots, results     and pub/sub
```

## Request flow

1. FastAPI validates a bounded request and applies an identity-specific rate limit.
2. The application hashes the opaque session token and opens a repository transaction.
3. Redis serializes the room command across instances, then PostgreSQL locks the room row. The saved snapshot is hydrated into the existing engine.
4. The engine validates and mutates state; repositories append action, event, result, and idempotency records.
5. The room snapshot and optimistic revision commit atomically.
6. Redis publishes only the room code and committed version—never hidden decisions.
7. Every app instance reloads a separate viewer-filtered projection for each local socket.

The Redis lease reduces cross-instance contention; PostgreSQL row locking remains the correctness mechanism if a lease expires. SQLAlchemy revision checks add an optimistic guard and SQLite test safety. Unique constraints protect action idempotency, event order, round results, and snapshot versions.

The database adapter is selected entirely from `DATABASE_URL`. PostgreSQL uses `asyncpg` and a configured connection pool. SQLite uses `aiosqlite`, enforced foreign keys, WAL mode for file databases, a busy timeout, and the same repositories and migrations. SQLite is a single-replica deployment option; multi-instance deployments require PostgreSQL.

## Failure boundaries

- Invalid domain commands roll back the complete SQL transaction.
- A repeated idempotency key returns its persisted response without another mutation.
- A failed Redis notification does not undo a committed database transaction; clients recover through the HTTP fallback.
- `/api/health` proves only that the process responds. `/api/ready` checks dependencies for traffic admission.
- Idle expiry is stored in SQL and checked on access. Each instance may scan; row locks with `SKIP LOCKED` ensure cooperative cleanup.

## Privacy and trust

The database is authoritative. Redis values are disposable. Browser-provided balances, outcomes, and scores are never trusted. Session plaintext is returned once and is not persisted or included in application access logs. Query-string access logs are disabled because WebSocket and compatibility HTTP reads carry credentials there.

See [data-model.md](data-model.md) for persistence details and [ADR 0001](adr/0001-durable-modular-monolith.md) for the decision rationale.
