"""High-entropy player session credential issuance and verification hashing."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class IssuedCredential:
    token: str
    token_hash: str
    expires_at: datetime


class SessionService:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)

    def issue(self) -> IssuedCredential:
        token = secrets.token_urlsafe(32)
        return IssuedCredential(token, self.hash_token(token), datetime.now(timezone.utc) + self.ttl)

    @staticmethod
    def hash_token(token: str) -> str:
        if not isinstance(token, str) or not 20 <= len(token) <= 256:
            return hashlib.sha256(b"invalid-player-token").hexdigest()
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
