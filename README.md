# Psychological Games — Loss Aversion Arcade

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A dependency-light, server-authoritative local multiplayer arcade for exploring decision-making under pressure. It is designed to be readable, hackable, and safe to extend.

This project turns all five concepts from `Psychology_Loss_Aversion_Games.md` into a locally playable multiplayer arcade. Players first choose a game, read a visual four-step explanation, create or join a room, and play through server-authoritative rounds.

The full source extraction—including original rules and unresolved design questions—is in [GAME_CATALOG.md](GAME_CATALOG.md).

## Included games

| Game | Playable MVP loop | End condition |
|---|---|---|
| The Vault | Lock wealth, use keys/seals, and survive liquidity-sensitive events | 5 rounds |
| The Burden | Split all wealth across protected, exposed, and transferred allocations | 6 rounds |
| Chain of Responsibility | Carry, pass, refuse, redirect, or bank an increasingly risky Charge | 8 chains or 5 ruptures |
| Insurance Market | Manipulate shared threat, buy protection, or accept underwriting obligations | 5 cycles |
| Reputation Economy | Spend identity on ambitions, promises, support, challenges, or conservation | 5 crises |

Every game has its own starting resources, hidden server state, legal actions, collective consequences, result summaries, and final score calculation. The interface explains the objective, round sequence, resources, and score before room creation. A **How to play** control makes the same guide available in the lobby and during play.

## Architecture

```text
Browser tab
  TypeScript UI
  ├─ game catalog and visual rule guides
  ├─ game-specific decision forms
  ├─ per-tab anonymous identity
  └─ room-state WebSocket updates with 5-second HTTP fallback
             │ player intentions as JSON
             ▼
FastAPI + Pydantic + Uvicorn                       backend/server.py
  ├─ typed JSON request validation
  ├─ OpenAPI documentation and health endpoint
  ├─ static frontend delivery
  └─ consistent JSON error responses
             │ validated commands
             ▼
Server-authoritative game engine                  backend/game.py
  ├─ room lifecycle and player identities
  ├─ five independent rules/resolution branches
  ├─ hidden random values and collective pressure
  ├─ idempotent one-action-per-round mutations
  ├─ viewer-specific privacy filtering
  └─ game-specific final scoring
```

The browser submits choices only. It never submits balances, random outcomes, collective pressure, or scores. The Python engine validates every choice, resolves the round under a process-wide lock, and returns a viewer-specific state projection. Exact opponent vault holdings remain hidden until the final reveal, and Chain risk clues are private to each viewer.

Rooms live in memory and disappear when the Python process stops. This is intentional for a dependency-light local MVP.

### Important files

| Path | Responsibility |
|---|---|
| `backend/game.py` | Shared room lifecycle plus five game rule engines |
| `backend/server.py` | FastAPI routes, Pydantic schemas, static files, and Uvicorn entry point |
| `frontend/src/main.ts` | Catalog, instruction guides, typed API client, and all game interfaces |
| `frontend/styles.css` | Responsive catalog, guides, rooms, decisions, and results |
| `tests/test_game.py` | Full-session coverage for every game plus authority/privacy checks |
| `GAME_CATALOG.md` | Detailed extraction of the original source document |

## Requirements

- Python 3.10 or newer.
- Node.js 18 or newer with npm.

Python dependencies are FastAPI and Uvicorn. TypeScript is the sole npm development dependency.

## Install and run

From this directory:

```powershell
python -m pip install -r requirements.txt
npm install
npm run build
python -m backend.server
```

Open <http://127.0.0.1:8000>.

FastAPI’s interactive API documentation is available at <http://127.0.0.1:8000/docs>, and the health check is at <http://127.0.0.1:8000/api/health>.

1. Select one of the five game cards.
2. Read its objective and four-step explanation.
3. Enter a name and create the room.
4. Open another tab, enter a different name, and join with the five-letter code.
5. Once everyone understands the rules, the host starts the game.

Identity is stored in `sessionStorage`, so separate tabs can represent separate local players. The source design targets 3–10 players; this MVP permits 2–10 to make solo testing practical.

To use another port:

```powershell
python -m backend.server --port 8080
```

After changing `frontend/src/main.ts`, rebuild it:

```powershell
npm run build
```

For backend development with automatic Python reloads:

```powershell
python -m uvicorn backend.server:app --reload
```

### If the page does not load

- If the page says **Server offline**, confirm `python -m backend.server` is still running in its terminal.
- If the page is blank or shows an old interface, run `npm run build` and hard-refresh the browser.
- If port 8000 is occupied, run `python -m backend.server --port 8080` and open <http://127.0.0.1:8080>.
- Check <http://127.0.0.1:8000/api/health>. A working server returns `{"status":"ok", ...}`.
- Check <http://127.0.0.1:8000/docs> to exercise the API directly.

## Verify

```powershell
npm run check
python -m unittest discover -v
```

The automated suite runs all five games from lobby to final score and checks the FastAPI routes, static app delivery, request validation, host authority, idempotency, invalid game rejection, and private Vault information.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/rooms` | Create a room with `name` and `gameId` |
| `POST` | `/api/rooms/{code}/join` | Join the selected game’s lobby |
| `GET` | `/api/rooms/{code}?playerId=…` | Fetch viewer-filtered room state |
| `POST` | `/api/rooms/{code}/start` | Host starts the first round |
| `POST` | `/api/rooms/{code}/actions` | Submit one game-specific private decision |
| `POST` | `/api/rooms/{code}/resolve` | Resolve absent players with safe defaults |
| `POST` | `/api/rooms/{code}/next` | Advance the room or reveal final scores |

Action requests use this common envelope:

```json
{
  "playerId": "anonymous-player-token",
  "idempotencyKey": "unique-client-generated-id",
  "values": {
    "gameSpecificChoice": "..."
  }
}
```

## MVP interpretations

The source document mixes detailed rules with high-level concepts. Where exact values were missing, the MVP uses explicit, testable interpretations:

- **The Vault:** hidden severity is 8–18; room liquidity below 30% is scarce and above 70% is exposed; keys withdraw 20%; seals cap liquid loss at 5%.
- **The Burden:** all three allocations must equal current wealth; the documented exposure bands are implemented; burden conditions slightly modify the exposed return; support before a negative resolution awards 5 points.
- **Chain of Responsibility:** each chain uses simultaneous stances for this local MVP; carrying increases shared rupture probability; Courage is worth 10 and Breaker Marks cost 5.
- **Insurance Market:** market actions move a hidden shared probability; bought policies reduce disaster asset loss; underwriting creates automatic obligations and insolvency penalties.
- **Reputation Economy:** spent reputation enters one pool; support votes determine its recipient; otherwise it returns to the player with the most remaining reputation; matching the crisis’s hidden favored action earns alignment.
- Missing players receive a conservative, game-specific action when the host forces resolution.

The following production-depth systems remain deferred: direct negotiation/chat, timed phases, Chain receiver acceptance handshakes, player-authored insurance contracts, public promise authoring, key trading, Rescue voting, named possessions, persistent replay storage, reconnection after server restart, room expiry, and rate limiting.

## Production path

Keep the game-rule boundary in `backend/game.py`, move rooms and actions into PostgreSQL transactions, add server deadlines, and broadcast committed room versions through a realtime provider. Anonymous tokens should become hashed expiring credentials. Direct negotiation mechanics should use an append-only event stream so disputes, reconnects, and replays remain deterministic.
