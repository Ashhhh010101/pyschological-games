# Contributing

Thanks for helping improve Psychological Games. Keep gameplay server-authoritative: the browser may submit intent, but balances, random outcomes, privacy filtering, and scores belong in `backend/game.py`.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
npm ci
npm run check
npm run build
python -m ruff check backend tests
python -m ruff format --check backend tests
python -m mypy backend
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
```

Keep pull requests focused, document rule changes in `GAME_CATALOG.md` or the README, and add a regression test for changed game behavior or API contracts.

## Design principles

- Rules should be deterministic under an injected random source.
- A player must never receive another player’s hidden state.
- Invalid actions fail clearly and do not partially mutate a room.
- UI changes should remain keyboard accessible and usable on narrow screens.

## Pull requests

Create a focused branch, use imperative commit messages, and explain both the change and its verification. Do not commit virtual environments, `node_modules`, frontend build output, secrets, or editor state. By contributing, you agree that your work is licensed under the repository’s MIT License.
