"""SSE investigation event log — replay across a dropped connection.

Regression cover for docs/audit.md A5. The bare-asyncio.Queue version this
replaced lost events on any mid-run disconnect: the stream's `finally` popped
the queue from the registry while run_pipeline held a reference to that same,
now orphaned, object and kept putting events into it. A reconnect got a fresh
empty queue nothing was writing to and hung on keep-alive pings while the
investigation finished server-side.

No pytest-asyncio in this project, so each test drives its own event loop via
asyncio.run().
"""

import asyncio

import pytest

import main


@pytest.fixture(autouse=True)
def _clean_logs():
    main._investigation_logs.clear()
    yield
    main._investigation_logs.clear()


async def _drain(log, start=0, stop_on_done=True):
    """Collect (index, event) pairs, ignoring pings, until `done` or exhaustion."""
    out = []
    async for index, event in log.subscribe(start):
        if event.get("type") == "ping":
            continue
        out.append((index, event))
        if stop_on_done and event.get("type") == "done":
            break
    return out


def test_late_subscriber_replays_everything_already_emitted():
    """A stream that attaches after the run started still sees the whole log."""
    async def scenario():
        log = main.InvestigationLog()
        await log.put({"type": "agent_start", "agent": "damage_assessment"})
        await log.put({"type": "agent_done", "agent": "damage_assessment"})
        await log.put({"type": "done", "summary": {"decision": "Approve"}})
        return await _drain(log)

    events = asyncio.run(scenario())
    assert [e["type"] for _, e in events] == ["agent_start", "agent_done", "done"]
    assert [i for i, _ in events] == [0, 1, 2]


def test_events_emitted_while_disconnected_are_delivered_on_reconnect():
    """The actual A5 bug: events produced during the gap must not be lost."""
    async def scenario():
        log = main.InvestigationLog()
        await log.put({"type": "agent_start", "agent": "damage_assessment"})

        # First connection sees event 0, then drops (generator closed).
        seen = []
        agen = log.subscribe(0)
        index, event = await agen.__anext__()
        seen.append((index, event))
        await agen.aclose()                      # client disconnected

        # The pipeline keeps running and emitting into the SAME log.
        await log.put({"type": "agent_done", "agent": "damage_assessment"})
        await log.put({"type": "agent_start", "agent": "fraud_intelligence"})
        await log.put({"type": "done", "summary": {"decision": "Approve"}})

        # Reconnect resumes after the last id the client actually received.
        resumed = await _drain(log, start=seen[-1][0] + 1)
        return seen, resumed

    seen, resumed = asyncio.run(scenario())
    assert [e["type"] for _, e in seen] == ["agent_start"]
    # Nothing missed, nothing duplicated.
    assert [e["type"] for _, e in resumed] == ["agent_done", "agent_start", "done"]


def test_log_survives_having_no_subscribers_at_all():
    """A disconnect must not orphan the log the pipeline is writing to."""
    async def scenario():
        log = main.get_investigation_log("CLM-TEST-1")
        for i in range(3):
            await log.put({"type": "agent_done", "agent": f"a{i}"})
        await log.put({"type": "done", "summary": {}})
        # Registry still holds the SAME object the writer used — the old code
        # popped it here, so a reconnect got a different, empty queue.
        assert main.get_investigation_log("CLM-TEST-1") is log
        return await _drain(log)

    events = asyncio.run(scenario())
    assert len(events) == 4
    assert events[-1][1]["type"] == "done"


def test_live_subscriber_wakes_on_new_events_and_ends_on_done():
    """A connected stream receives events as they are produced, then terminates."""
    async def scenario():
        log = main.InvestigationLog()
        collected = []

        async def reader():
            async for index, event in log.subscribe(0):
                if event.get("type") == "ping":
                    continue
                collected.append(event["type"])
                if event.get("type") == "done":
                    return

        task = asyncio.create_task(reader())
        await asyncio.sleep(0)                   # let the reader block on the waiter
        await log.put({"type": "agent_start", "agent": "x"})
        await asyncio.sleep(0)
        await log.put({"type": "done", "summary": {}})
        await asyncio.wait_for(task, timeout=2)  # subscribe() must return on done
        return collected

    assert asyncio.run(scenario()) == ["agent_start", "done"]


def test_done_marks_the_log_finished():
    async def scenario():
        log = main.InvestigationLog()
        await log.put({"type": "agent_start", "agent": "x"})
        assert log.finished is False
        await log.put({"type": "done", "summary": {}})
        return log.finished

    assert asyncio.run(scenario()) is True


def test_new_log_per_run_so_a_reinvestigation_does_not_replay_the_old_one():
    async def scenario():
        first = main.new_investigation_log("CLM-TEST-2")
        await first.put({"type": "agent_done", "agent": "stale"})
        await first.put({"type": "done", "summary": {}})

        second = main.new_investigation_log("CLM-TEST-2")
        assert second is not first
        return second.events

    assert asyncio.run(scenario()) == []


def test_sse_wire_emits_ids_and_honours_last_event_id():
    """The wire contract the browser's own auto-reconnect depends on.

    EventSource replays `Last-Event-ID` on reconnect; without an `id:` on each
    event there is nothing for it to send, and the server would have to choose
    between re-sending the whole run or losing the gap.
    """
    async def scenario():
        import httpx

        log = main.new_investigation_log("CLM-WIRE-1")
        await log.put({"type": "agent_start", "agent": "damage_assessment"})
        await log.put({"type": "agent_done", "agent": "damage_assessment"})
        await log.put({"type": "done", "summary": {"decision": "Approve"}})

        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            fresh = await client.get("/api/claims/CLM-WIRE-1/stream")
            resumed = await client.get("/api/claims/CLM-WIRE-1/stream",
                                       headers={"Last-Event-ID": "0"})
        return fresh.text, resumed.text

    fresh, resumed = asyncio.run(scenario())

    # A first connection replays the whole log, each event carrying its index.
    for i in range(3):
        assert f"id: {i}" in fresh
    # A reconnect resumes strictly AFTER the last id the client acknowledged.
    assert "id: 0" not in resumed          # not re-sent
    assert "id: 1" in resumed              # the gap is delivered
    assert "id: 2" in resumed


def test_prune_drops_only_finished_logs():
    """Retention is bounded, but a run still in flight is never discarded."""
    async def scenario():
        for i in range(main._MAX_RETAINED_LOGS + 5):
            log = main.new_investigation_log(f"CLM-FIN-{i}")
            await log.put({"type": "done", "summary": {}})     # finished
        in_flight = main.new_investigation_log("CLM-RUNNING")
        await in_flight.put({"type": "agent_start", "agent": "x"})  # unfinished
        for i in range(10):                                    # force pruning
            main.new_investigation_log(f"CLM-EXTRA-{i}")
        return "CLM-RUNNING" in main._investigation_logs

    assert asyncio.run(scenario()) is True


# ── Navigating away must not affect the run ───────────────────────────────────
# Reported: "if we start the investigation and go back, the investigation stops
# or happened in a sec." Nothing was actually stopping — the pipeline is a
# server-side background task and InvestigationLog.put() only appends to a list,
# so a departed client cannot stall it. The client simply had no way to ASK
# whether a run was in flight, so on returning it opened no stream: the agents
# already written to result.json rendered as "Done" and the rest sat on
# "Waiting", which reads as an investigation that died or finished instantly.

import asyncio

import pytest

import main


async def _drain_types(log, limit=None):
    """Consume events, optionally leaving early to simulate navigating away."""
    seen = []
    async for idx, ev in log.subscribe(0):
        if idx is None:          # keep-alive ping, not part of the log
            continue
        seen.append(ev["type"])
        if limit and len(seen) >= limit:
            break
    return seen


async def _emit(log):
    for agent in ("eligibility_screen", "damage_assessment", "fraud_intelligence"):
        await log.put({"type": "agent_start", "agent": agent})
        await asyncio.sleep(0)
        await log.put({"type": "agent_done", "agent": agent, "result": {"status": "completed"}})
    await log.put({"type": "done"})


def test_run_completes_with_no_subscriber_at_all():
    """The whole point: nobody is watching and the pipeline still finishes."""
    async def go():
        log = main.new_investigation_log("CLM-NOBODY")
        await _emit(log)
        return log
    log = asyncio.run(go())
    assert log.finished is True
    assert sum(1 for e in log.events if e["type"] == "agent_done") == 3


def test_client_leaving_mid_run_does_not_stall_the_pipeline():
    async def go():
        log = main.new_investigation_log("CLM-LEAVE")
        task = asyncio.create_task(_emit(log))
        left_after = await _drain_types(log, limit=2)     # navigate away
        await task                                   # run continues regardless
        return log, left_after
    log, left_after = asyncio.run(go())
    assert len(left_after) == 2
    assert log.finished is True
    assert log.events[-1]["type"] == "done"


def test_returning_client_replays_the_entire_run():
    """A late attach sends no Last-Event-ID, so the backend replays from 0."""
    async def go():
        log = main.new_investigation_log("CLM-RETURN")
        task = asyncio.create_task(_emit(log))
        await _drain_types(log, limit=2)
        await task
        return await _drain_types(log)                      # the user comes back
    replayed = asyncio.run(go())
    assert replayed[-1] == "done", "the terminal event must be replayed"
    assert replayed.count("agent_done") == 3, "every agent must be replayed"


# ── The status endpoint the client was missing ────────────────────────────────

def test_status_reports_running_while_in_flight():
    async def go():
        log = main.new_investigation_log("CLM-STATUS")
        await log.put({"type": "agent_start", "agent": "damage_assessment"})
        return main.investigation_status("CLM-STATUS")
    st = asyncio.run(go())
    assert st["running"] is True and st["finished"] is False
    assert st["event_count"] == 1


def test_status_reports_finished_after_the_terminal_event():
    async def go():
        log = main.new_investigation_log("CLM-FINISHED")
        await _emit(log)
        return main.investigation_status("CLM-FINISHED")
    st = asyncio.run(go())
    assert st["running"] is False and st["finished"] is True


def test_status_for_a_claim_never_investigated_is_not_running():
    """Critical: the hook attaches only when running is True. If an unknown
    claim reported running, the UI would open a stream that never emits and sit
    on 'Investigating…' forever."""
    st = main.investigation_status("CLM-DOES-NOT-EXIST")
    assert st["running"] is False
    assert st["known"] is False
    assert st["event_count"] == 0


def test_an_in_flight_log_is_never_pruned():
    """Retention must not drop a run that is still going."""
    async def go():
        live = main.new_investigation_log("CLM-KEEPME")
        await live.put({"type": "agent_start", "agent": "damage_assessment"})
        for i in range(main._MAX_RETAINED_LOGS + 10):
            finished = main.new_investigation_log(f"CLM-DONE-{i}")
            await finished.put({"type": "done"})
        return main.investigation_status("CLM-KEEPME")
    st = asyncio.run(go())
    assert st["running"] is True, "an unfinished run was pruned"
