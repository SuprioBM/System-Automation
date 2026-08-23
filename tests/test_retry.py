import pytest

from app.core.retry import with_retries


class Flaky(Exception):
    pass


def test_retries_until_success_within_budget():
    calls = {"n": 0}

    @with_retries("test_service", "op", exceptions=(Flaky,), attempts=3)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Flaky("not yet")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_gives_up_after_exhausting_attempts():
    calls = {"n": 0}

    @with_retries("test_service", "op", exceptions=(Flaky,), attempts=2)
    def always_fails():
        calls["n"] += 1
        raise Flaky("nope")

    with pytest.raises(Flaky):
        always_fails()
    assert calls["n"] == 2


def test_non_retryable_exception_is_not_retried():
    calls = {"n": 0}

    @with_retries("test_service", "op", exceptions=(Flaky,), attempts=3)
    def raises_other():
        calls["n"] += 1
        raise ValueError("unrelated")

    with pytest.raises(ValueError):
        raises_other()
    assert calls["n"] == 1
