"""Stable application errors safe to map to public API responses."""


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"


class RoomNotFound(ApplicationError):
    code = "ROOM_NOT_FOUND"


class PlayerNotFound(ApplicationError):
    code = "PLAYER_NOT_FOUND"


class UnauthorizedPlayer(ApplicationError):
    code = "UNAUTHORIZED_PLAYER"


class InvalidGameAction(ApplicationError):
    code = "INVALID_GAME_ACTION"


class DuplicateAction(ApplicationError):
    code = "DUPLICATE_ACTION"


class RoundAlreadyResolved(ApplicationError):
    code = "ROUND_ALREADY_RESOLVED"


class RoomExpired(ApplicationError):
    code = "ROOM_EXPIRED"


class RateLimitExceeded(ApplicationError):
    code = "RATE_LIMIT_EXCEEDED"


class PersistenceError(ApplicationError):
    code = "PERSISTENCE_ERROR"


class ConcurrentMutation(ApplicationError):
    code = "CONCURRENT_MUTATION"
