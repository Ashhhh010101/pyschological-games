# Deployment guide

## Single-host Compose

1. Copy `.env.example` to `.env`.
2. Set a strong, unique `POSTGRES_PASSWORD` and the public `ALLOWED_ORIGINS`/`TRUSTED_HOSTS` values.
3. Run `docker compose pull` and `docker compose up --build -d`.
4. Confirm `docker compose ps`, `/api/health`, and `/api/ready`.
5. Terminate TLS at a maintained reverse proxy. Enable `TRUST_PROXY_HEADERS` only when direct client access to the app port is blocked.

The `migrate` service applies Alembic before `app` is admitted. PostgreSQL and Redis persist in named volumes. The app filesystem is read-only, runs without root, and has `no-new-privileges`.

## SQLite deployment

For a small single-instance installation, use the SQLite override:

```console
docker compose -f compose.yaml -f compose.sqlite.yaml up --build -d
```

This selects the async SQLite driver at runtime, mounts the same `sqlite-data` volume into the migration and app containers, and disables the PostgreSQL service. The database factory enables foreign keys, a busy timeout, WAL mode, and normal synchronous durability. Back up the named volume or its database file before upgrades.

Do not scale SQLite-backed app containers or place the database on a network filesystem. Switch `DATABASE_URL` to `postgresql+asyncpg://...`, migrate the data through a reviewed procedure, and use the base Compose topology for horizontal scaling.

## Horizontal scaling

All replicas must use the same PostgreSQL database, Redis database/prefix, signing-independent session policy, and schema revision. SQLite is not supported for this topology. Scale only the `app` service:

```console
docker compose up -d --scale app=3
```

Place a reverse proxy/load balancer in front; sticky sessions are unnecessary because WebSocket changes are published through Redis and every projection reloads from SQL. Do not publish app replica ports individually with the default Compose port mapping when scaling—use an internal proxy configuration.

## Observability

Set `OTEL_ENABLED=true` and an OTLP endpoint. The optional Compose profile is diagnostic:

```console
docker compose --profile observability up -d
docker compose logs -f otel-collector
```

Production deployments should replace the debug exporter with an authenticated observability backend. Logs go to stdout as JSON and include request ID, room code, operation, latency, and active trace IDs. They intentionally omit bodies, session tokens, decisions, and query strings.

## Backups and upgrades

- Back up PostgreSQL before application or schema upgrades; test restoration regularly.
- Redis persistence improves continuity but Redis remains disposable coordination state.
- Build immutable tagged images. Run migrations as a controlled one-shot job before rolling app replicas.
- Review every migration’s downgrade and lock impact. Large-table changes may need an online migration plan.
- Roll back the app image only when its code is compatible with the current schema; otherwise apply the reviewed downgrade first.

See [operations runbook](runbooks/operations.md) for incident procedures.
