# Security policy

This is a self-hostable multiplayer game. Its anonymous player session token authorizes one player inside one room; it is not a general user account. Tokens are high-entropy, expire, and are stored as hashes, but possession grants room access until expiry. Do not share them or include them in support reports.

The supported public deployment posture is PostgreSQL plus Redis behind an HTTPS reverse proxy, with explicit `ALLOWED_ORIGINS` and `TRUSTED_HOSTS`, protected database/Redis networks, strong credentials, backups, and current container images. Enable proxy-header trust only when the app cannot be reached around the trusted proxy. Review retention needs before storing sensitive player names or decisions.

The service implements bounded payloads, distributed endpoint rate limits, transactional idempotency, idle room expiry, stable safe errors, viewer-specific projections, and logs that omit bodies and query strings. Operators remain responsible for TLS, network policy, secrets management, denial-of-service protection at the edge, dependency updates, backup encryption, and access to telemetry and database records.

Only the latest commit on `main` receives security fixes. Dependency and container updates should be tested through the included CI workflow before deployment.

To report a security issue, open a private report with the repository maintainers rather than publishing exploit details in an issue.
