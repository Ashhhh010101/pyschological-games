# Security policy

This is a self-hostable, in-memory multiplayer prototype intended for local play or trusted private networks. The anonymous player token is a room credential, not a user account. Do not use the service for sensitive data or expose it directly to the public internet without authentication, rate limiting, durable storage controls, room expiry, and an HTTPS deployment boundary.

Only the latest commit on `main` receives security fixes. Dependency and container updates should be tested through the included CI workflow before deployment.

To report a security issue, open a private report with the repository maintainers rather than publishing exploit details in an issue.
