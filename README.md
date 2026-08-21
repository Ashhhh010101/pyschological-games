# Psychological Games — Loss Aversion Arcade

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A self-hostable, server-authoritative multiplayer arcade for exploring decisions under pressure. Five games share a TypeScript browser client and a production-oriented FastAPI modular monolith with durable rooms, secure anonymous sessions, multi-instance WebSockets, rate limits, and observability.

## Games

| Game | Core decision | End condition |
|---|---|---|
| The Vault | Balance liquid and protected wealth against hidden events | 5 rounds |
| The Burden | Allocate wealth across protection, exposure, and transfers | 6 rounds |
| Chain of Responsibility | Carry, pass, or reject an increasingly risky charge | 8 chains or 5 ruptures |
| Insurance Market | Change shared risk and accept correlated obligations | 5 cycles |
| Reputation Economy | Spend reputation on identity, promises, and influence | 5 crises |

The rules remain isolated in `backend/game.py`. The browser submits intentions only; balances, randomness, resolution, privacy filtering, and scores remain authoritative on the server.

## Stack

- TypeScript browser client, compiled with TypeScript 5
- Python 3.10+ with FastAPI, Pydantic Settings, and Uvicorn
- SQLAlchemy 2 async repositories and Alembic migrations
- PostgreSQL in production; SQLite for zero-service local development and tests
- Redis for room TTL markers, distributed locks/rate limits, and pub/sub fan-out
- OpenTelemetry traces and metrics plus correlation-aware JSON logs
- Docker Compose, GitHub Actions, Ruff, mypy, Coverage, and unittest

See [architecture](docs/architecture.md), [data model](docs/data-model.md), and the [persistence decision record](docs/adr/0001-durable-modular-monolith.md).

## Self-host with Docker Compose

Requirements: Docker Engine with Compose v2.

```console
cp .env.example .env
docker compose up --build -d
docker compose ps
```

On PowerShell, use `Copy-Item .env.example .env`. Set a strong `POSTGRES_PASSWORD` in `.env` before exposing the deployment. Open <http://127.0.0.1:8000>; readiness is at <http://127.0.0.1:8000/api/ready>.

Compose starts a one-shot migration container, PostgreSQL, Redis, and the non-root read-only app container. PostgreSQL and Redis use named volumes. To include the bundled diagnostic OpenTelemetry collector:

```console
docker compose --profile observability up --build -d
```

Set `OTEL_ENABLED=true` in `.env`. The bundled collector writes concise telemetry to its logs; replace its exporter configuration for a production backend. Operational procedures are in [deployment](docs/deployment.md) and the [runbooks](docs/runbooks/operations.md).

For a lightweight single-instance deployment backed by persistent SQLite instead of PostgreSQL:

```console
docker compose -f compose.yaml -f compose.sqlite.yaml up --build -d
```

The override selects `sqlite+aiosqlite:////app/data/psychological_games.db`, persists it in the `sqlite-data` volume, and omits PostgreSQL. Alembic uses the same runtime URL. SQLite mode is intended for one app replica; choose PostgreSQL before scaling horizontally.

## Local development

SQLite and in-process coordination are the defaults, so PostgreSQL and Redis are optional for a single developer process.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
npm ci
npm run build
python -m alembic upgrade head
python -m backend.server
```

On macOS or Linux, activate with `source .venv/bin/activate`. The UI is at <http://127.0.0.1:8000> and OpenAPI at <http://127.0.0.1:8000/docs>.

For backend reloads:

```console
python -m uvicorn backend.server:app --reload
```

For a fresh local schema, keep `APP_ENV=development`; the application can create SQLite tables. Alembic remains the source of truth for deployed schema changes.

## Configuration

All settings are environment-driven and validated at startup. See [.env.example](.env.example) for a deployable template.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test`, or `production` |
| `DATABASE_URL` | local async SQLite | Async SQLAlchemy URL; Compose supplies PostgreSQL |
| `COMPOSE_DATABASE_URL` | Compose PostgreSQL URL | Optional database override injected by base Compose |
| `SQLITE_WAL_ENABLED` | `true` | Use write-ahead logging for file-backed SQLite |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | Wait for a SQLite writer before returning lock errors |
| `REDIS_URL` | empty | Enables distributed cache, limits, and pub/sub |
| `ROOM_IDLE_TTL_SECONDS` | `3600` | Idle room expiry |
| `SESSION_TTL_SECONDS` | `86400` | Anonymous player credential lifetime |
| `PAYLOAD_MAX_BYTES` | `65536` | Maximum HTTP request body |
| `ALLOWED_ORIGINS` | empty | Comma-separated CORS allowlist |
| `TRUSTED_HOSTS` | `*` | Comma-separated Host header allowlist |
| `TRUST_PROXY_HEADERS` | `false` | Honor proxy client headers only when explicitly enabled |
| `LOG_JSON` | `true` | Emit structured logs |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry instrumentation |

Rate limits for room creation, joining, actions, resolution, and WebSocket connections are independently configurable. Never commit `.env` or production credentials.

## API contract

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Process liveness only |
| `GET` | `/api/ready` | Database, cache, and event-bus readiness |
| `POST` | `/api/rooms` | Create a room and issue its host session token |
| `POST` | `/api/rooms/{code}/join` | Join a lobby and issue a player session token |
| `GET` | `/api/rooms/{code}?playerId=…` | Read a viewer-filtered projection |
| `POST` | `/api/rooms/{code}/start` | Start a game as host |
| `POST` | `/api/rooms/{code}/actions` | Submit one private round action |
| `POST` | `/api/rooms/{code}/resolve` | Resolve missing actions with safe defaults |
| `POST` | `/api/rooms/{code}/next` | Advance or finish the game |
| `WS` | `/api/rooms/{code}/ws?playerId=…` | Receive viewer-specific committed versions |

`playerId` is retained as a compatibility field name but contains an opaque high-entropy session token. Only its SHA-256 hash is persisted. Mutating requests accept a client-generated `idempotencyKey`; action requests require one. Errors use a stable envelope:

```json
{"error":{"code":"ROOM_NOT_FOUND","message":"Room not found."}}
```

## Verification

```powershell
python -m ruff check backend tests alembic
python -m ruff format --check backend tests alembic
python -m mypy backend
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
npm test
npm run build
docker compose config --quiet
```

PostgreSQL and Redis integration tests run automatically in CI. Locally, set `TEST_DATABASE_URL` and `TEST_REDIS_URL` to enable them.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes and [SECURITY.md](SECURITY.md) before exposing the service. Game mechanics and interpretations are documented in [GAME_CATALOG.md](GAME_CATALOG.md).

This repository is licensed under the [MIT License](LICENSE).
