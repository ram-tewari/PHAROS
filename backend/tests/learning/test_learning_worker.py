"""The learning worker waits for the database instead of failing a scheduled run."""

from contextlib import contextmanager

from sqlalchemy.exc import OperationalError

from app.workers import learning_worker


class _Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self):
        return self.now


def _scope_failing(times: int):
    calls = {"n": 0}

    class _DB:
        def execute(self, _stmt):
            calls["n"] += 1
            if calls["n"] <= times:
                raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))

    @contextmanager
    def scope():
        yield _DB()

    return scope, calls


def test_waits_until_the_database_answers(monkeypatch):
    scope, calls = _scope_failing(2)
    monkeypatch.setattr(learning_worker, "session_scope", scope)
    clock = _Clock()
    assert learning_worker.wait_for_database(600, sleep=clock.sleep, clock=clock) is True
    assert calls["n"] == 3 and clock.sleeps == [5.0, 10.0]


def test_gives_up_after_the_timeout(monkeypatch):
    scope, _ = _scope_failing(10_000)
    monkeypatch.setattr(learning_worker, "session_scope", scope)
    clock = _Clock()
    assert learning_worker.wait_for_database(120, sleep=clock.sleep, clock=clock) is False
    assert clock.now <= 120 and clock.sleeps[-1] <= 60
