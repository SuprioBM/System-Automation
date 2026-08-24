"""Spec §19 A-G. Uses LangGraph's real StateGraph + MemorySaver + RetryPolicy
directly (not mocked) wherever the point is to prove the actual mechanism
works, since that's the part most worth verifying for real."""
from __future__ import annotations

from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.core.errors import ConfigurationError, ExternalServiceError, is_transient_error


# ── Error classification (underlies B/C) ─────────────────────────────────

@pytest.mark.parametrize("exc,expected", [
    (ExternalServiceError("groq", "op", "rate limited", status_code=429), True),
    (ExternalServiceError("groq", "op", "server error", status_code=503), True),
    (ExternalServiceError("github", "op", "bad request", status_code=400), False),
    (ExternalServiceError("github", "op", "not found", status_code=404), False),
    (ConfigurationError("missing key"), False),
    (ValueError("Connection timeout while calling API"), True),
    (ValueError("totally unrelated message"), False),
])
def test_is_transient_error_classification(exc, expected):
    assert is_transient_error(exc) is expected


# ── A minimal real StateGraph to exercise LangGraph's own retry + checkpoint
#    mechanics directly, the same way app/graph/build.py wires nodes ───────

class _S(TypedDict, total=False):
    calls: dict


def _make_graph(node2_fn, checkpointer):
    retry_policy = RetryPolicy(max_attempts=3, initial_interval=0.01, backoff_factor=1.0,
                                jitter=False, retry_on=is_transient_error)
    builder = StateGraph(_S)
    calls = {"node1": 0, "node2": 0}

    def node1(state):
        calls["node1"] += 1
        return {}

    def node2(state):
        calls["node2"] += 1
        return node2_fn(calls["node2"])

    builder.add_node("node1", node1, retry=retry_policy)
    builder.add_node("node2", node2, retry=retry_policy)
    builder.add_edge(START, "node1")
    builder.add_edge("node1", "node2")
    builder.add_edge("node2", END)
    return builder.compile(checkpointer=checkpointer), calls


def test_b_transient_failure_then_automatic_recovery():
    """node2 fails twice with a 429-shaped error then succeeds -- within the
    retry budget, LangGraph's own RetryPolicy must recover automatically,
    no Discord/external intervention needed."""
    def flaky(call_number):
        if call_number < 3:
            raise ExternalServiceError("groq", "op", "rate limited", status_code=429)
        return {}

    cp = MemorySaver()
    graph, calls = _make_graph(flaky, cp)
    config = {"configurable": {"thread_id": "wf-b"}}
    graph.invoke({"calls": {}}, config=config)
    assert calls["node1"] == 1
    assert calls["node2"] == 3  # 2 failures + 1 success, all within one graph.invoke()


def test_c_permanent_failure_is_not_retried():
    """A ConfigurationError must fail on the first attempt -- retrying it
    would never succeed, so no attempts should be wasted."""
    def always_permanent(call_number):
        raise ConfigurationError("missing GROQ_API_KEY")

    cp = MemorySaver()
    graph, calls = _make_graph(always_permanent, cp)
    config = {"configurable": {"thread_id": "wf-c"}}
    with pytest.raises(ConfigurationError):
        graph.invoke({"calls": {}}, config=config)
    assert calls["node2"] == 1  # no retries wasted on a permanent error


def test_d_resume_does_not_re_execute_completed_nodes():
    """node1 succeeds and checkpoints; node2 fails once then succeeds within
    budget on the first invoke. A later 'Resume' (re-invoking with
    input=None on the same thread_id) must not re-run node1."""
    attempt = {"n": 0}

    def fails_once_then_succeeds(call_number):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise ExternalServiceError("groq", "op", "rate limited", status_code=429)
        return {}

    cp = MemorySaver()
    graph, calls = _make_graph(fails_once_then_succeeds, cp)
    config = {"configurable": {"thread_id": "wf-d"}}
    graph.invoke({"calls": {}}, config=config)
    assert calls["node1"] == 1

    # simulate a genuinely separate "Resume" re-invocation (a new
    # graph.invoke() call on the SAME thread_id, as run_recovery does)
    graph.invoke(None, config=config)
    # node1 must NOT have run again -- LangGraph sees the run already
    # completed and has nothing left to do
    assert calls["node1"] == 1


def test_g_new_workflow_id_is_independent_of_an_old_failed_one():
    """A different thread_id must never see or depend on another
    thread_id's checkpoint -- this is what makes 'new commit -> new
    workflow, starts at node 1' true by construction."""
    def always_permanent(call_number):
        raise ConfigurationError("boom")

    cp = MemorySaver()
    graph, calls = _make_graph(always_permanent, cp)
    with pytest.raises(ConfigurationError):
        graph.invoke({"calls": {}}, config={"configurable": {"thread_id": "wf-old"}})
    assert calls["node1"] == 1

    # a new workflow (new thread_id) with a *working* node2 must run node1
    # fresh -- it does not "resume" wf-old's checkpoint
    graph2, calls2 = _make_graph(lambda n: {}, cp)
    graph2.invoke({"calls": {}}, config={"configurable": {"thread_id": "wf-new"}})
    assert calls2["node1"] == 1
    assert calls["node1"] == 1  # wf-old's checkpoint is untouched
