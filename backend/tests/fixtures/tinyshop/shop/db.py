"""Tiny in-memory persistence layer."""

import threading

_USERS: dict[str, dict] = {}
_LOCK = threading.Lock()


class ConnectionPool:
    """A bounded pool of fake database connections."""

    def __init__(self, size: int = 4):
        self._free = list(range(size))
        self._cond = threading.Condition()

    def acquire(self, timeout: float = 5.0) -> int:
        """Block until a connection is free, then check it out."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._free, timeout=timeout):
                raise TimeoutError("connection pool exhausted")
            return self._free.pop()

    def release(self, conn: int) -> None:
        """Return a connection to the pool and wake one waiter."""
        with self._cond:
            self._free.append(conn)
            self._cond.notify()


def save_user(username: str, password_hash: str) -> dict:
    """Insert or replace a user record."""
    with _LOCK:
        user = {"id": len(_USERS) + 1, "username": username, "password_hash": password_hash}
        _USERS[username] = user
        return user


def fetch_user(username: str) -> dict | None:
    """Load a user record by username."""
    with _LOCK:
        return _USERS.get(username)
