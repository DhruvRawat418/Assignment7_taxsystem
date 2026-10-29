"""SilverFile memory layer: one place to inspect what the system remembers about a case.

What SilverFile remembers, and where (both are LangGraph SqliteSaver checkpoints,
one thread per case_id):

- ``intake_sessions.db``: the taxpayer interview. It holds every answer with its
  provenance, the correction history, volunteer notes, and the question the
  taxpayer is currently being asked.
- ``workflow_sessions.db``: the agent workflow (``CaseState``). It holds
  extractions (merged by an order-independent reducer), rules, computation,
  audit, model review, human decisions, and the list of visited stages.

This module is strictly READ-ONLY. It never invokes an agent, never writes a
checkpoint, and opens the databases with ``mode=ro`` and ``query_only``. It
backs four memory guarantees with code you can run:

- ``resume_recap``: what a returning taxpayer or staff member sees. It covers
  when the case was last touched, how long it has been idle, what was already
  covered, and what comes next. This is spec 4.3 (resumability).
- ``case_timeline``: the checkpoint history of both stores in time order,
  grouped into working sessions. It shows that a case paused on Tuesday
  continues on Friday from the same checkpoint.
- ``memory_footprint``: the checkpoint count and stored bytes per case, so
  state growth is measured rather than assumed.
- ``audit_persisted_memory``: scans every stored checkpoint and pending write
  for real-looking SSNs or API keys. These must never reach durable memory.

CLI::

    python -m src.memory recap     --root <data dir> --case <case_id>
    python -m src.memory timeline  --root <data dir> --case <case_id>
    python -m src.memory footprint --root <data dir> --case <case_id>
    python -m src.memory audit     --root <data dir>
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

INTAKE_DB = "intake_sessions.db"
WORKFLOW_DB = "workflow_sessions.db"
# Two checkpoints further apart than this belong to different working sessions.
SESSION_GAP = timedelta(minutes=30)


# --------------------------------------------------------------------------
# Read-only access to the two stores
# --------------------------------------------------------------------------
@contextmanager
def _readonly_saver(path: Path):
    """Same pattern as the dashboard: a strictly read-only SQLite connection."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                                 check_same_thread=False)) as connection:
        connection.execute("PRAGMA query_only=ON")
        saver = SqliteSaver(connection)
        saver.is_setup = True  # The schema belongs to the writer; never migrate here.
        saver._has_task_path = any(row[1] == "task_path" for row in
                                   connection.execute("PRAGMA table_info(writes)"))
        yield saver, connection


def _has_checkpoints(path: Path) -> bool:
    if not path.is_file():
        return False
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"checkpoints", "writes"}.issubset(names)


def _interview_graph(saver):
    from demo.run_intake import build_graph as build_interview
    from src.agents.intake_parser import RuleParser
    return build_interview(RuleParser(), saver)


def _workflow_graph(saver):
    from src.integration.graph import build_graph
    return build_graph(checkpointer=saver)


def _config(case_id: str) -> dict:
    from src.integration.case_service import validate_case_id
    return {"configurable": {"thread_id": validate_case_id(case_id)}}


def _pending(snapshot) -> list:
    return [i.value for task in snapshot.tasks for i in task.interrupts]


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _plain_duration(delta: timedelta) -> str:
    """'3 days', '5 hours', '12 minutes', 'less than a minute'. For people, not machines."""
    seconds = int(delta.total_seconds())
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''}"
    return "less than a minute"


# --------------------------------------------------------------------------
# 1. Resume recap
# --------------------------------------------------------------------------
def resume_recap(root, case_id: str, now: datetime | None = None) -> dict:
    """What someone coming back to this case should be told. Never shows a full SSN
    (it reuses the Intake agent's own summarize())."""
    from src.agents.intake import summarize

    root, now = Path(root), now or datetime.now(timezone.utc)
    recap: dict = {"case_id": case_id, "found": False}
    intake_path = root / INTAKE_DB
    if _has_checkpoints(intake_path):
        with _readonly_saver(intake_path) as (saver, _):
            graph = _interview_graph(saver)
            snapshot = graph.get_state(_config(case_id))
            if snapshot.values:
                history = list(graph.get_state_history(_config(case_id)))
                pending = _pending(snapshot)
                last = _parse(snapshot.created_at)
                recap.update(
                    found=True,
                    started_at=history[-1].created_at,
                    last_activity_at=snapshot.created_at,
                    idle_for=_plain_duration(now - last),
                    answers_saved=len(snapshot.values.get("answers", {})),
                    covered_so_far=summarize(snapshot.values) or "- nothing yet",
                    next_step=(pending[0].get("question") if pending and pending[0].get("type") == "ask_user"
                               else "waiting for staff review" if pending
                               else "interview complete" if snapshot.values.get("intake_complete")
                               else "interview paused"),
                )
    workflow_path = root / WORKFLOW_DB
    if _has_checkpoints(workflow_path):
        with _readonly_saver(workflow_path) as (saver, _):
            snapshot = _workflow_graph(saver).get_state(_config(case_id))
            if snapshot.values:
                pending = _pending(snapshot)
                recap["found"] = True
                recap["workflow"] = dict(
                    status="paused_for_human_review" if pending else snapshot.values.get("status"),
                    revision=snapshot.values.get("revision", 0),
                    stages_visited=len(snapshot.values.get("events", [])),
                    last_activity_at=snapshot.created_at,
                    pending_reviews=len(pending),
                )
    if recap["found"]:
        recap["message"] = _recap_message(recap)
    return recap


def _recap_message(recap: dict) -> str:
    if "last_activity_at" not in recap:
        w = recap["workflow"]
        return f"Workflow status: {w['status']} (revision {w['revision']})."
    lines = [f"Welcome back. We last worked on this {recap['idle_for']} ago.",
             "Here is what we already covered:", recap["covered_so_far"]]
    if recap["next_step"] not in {"interview complete", "interview paused", "waiting for staff review"}:
        lines.append(f"Let's pick up where we left off: {recap['next_step']}")
    else:
        lines.append(f"Status: {recap['next_step']}.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 2. Timeline
# --------------------------------------------------------------------------
def _intake_label(snapshot) -> str:
    pending = _pending(snapshot)
    if snapshot.metadata.get("source") == "input":
        return "interview started"
    if snapshot.metadata.get("source") == "update":
        return "saved answers updated by an explicit action"
    if pending and pending[0].get("type") == "ask_user":
        return f"waiting for answer: {pending[0].get('field')}"
    if pending:
        return "waiting for staff review"
    if snapshot.values.get("intake_complete"):
        return "interview complete"
    return "interview step"


def _workflow_label(snapshot) -> str:
    if _pending(snapshot):
        return "paused for human review"
    nxt = ", ".join(snapshot.next) if snapshot.next else ""
    status = snapshot.values.get("status", "")
    return f"next: {nxt}" if nxt else f"stopped at status: {status}"


def case_timeline(root, case_id: str) -> dict:
    """Both stores' checkpoints in time order, then grouped into working sessions."""
    root = Path(root)
    events = []
    for store, filename, build, label in (("interview", INTAKE_DB, _interview_graph, _intake_label),
                                          ("workflow", WORKFLOW_DB, _workflow_graph, _workflow_label)):
        path = root / filename
        if not _has_checkpoints(path):
            continue
        with _readonly_saver(path) as (saver, _):
            for snap in build(saver).get_state_history(_config(case_id)):
                events.append(dict(at=snap.created_at, store=store, step=snap.metadata.get("step"),
                                   checkpoint_id=snap.config["configurable"]["checkpoint_id"],
                                   what=label(snap)))
    events.sort(key=lambda e: (e["at"], e["store"]))
    sessions = []
    for event in events:
        at = _parse(event["at"])
        if not sessions or at - _parse(sessions[-1]["ended_at"]) > SESSION_GAP:
            sessions.append(dict(started_at=event["at"], ended_at=event["at"], checkpoints=0))
        sessions[-1]["ended_at"] = event["at"]
        sessions[-1]["checkpoints"] += 1
    for previous, current in zip(sessions, sessions[1:]):
        current["resumed_after"] = _plain_duration(_parse(current["started_at"]) - _parse(previous["ended_at"]))
    return {"case_id": case_id, "events": events, "sessions": sessions}


# --------------------------------------------------------------------------
# 3. Footprint
# --------------------------------------------------------------------------
def memory_footprint(root, case_id: str) -> dict:
    """How much the system stores for one case. Latest-state sizes are what the agents
    actually work from; the checkpoint history is kept for audit and resume."""
    root = Path(root)
    report = {"case_id": case_id}
    for store, filename, build in (("interview", INTAKE_DB, _interview_graph),
                                   ("workflow", WORKFLOW_DB, _workflow_graph)):
        path = root / filename
        if not _has_checkpoints(path):
            continue
        with _readonly_saver(path) as (saver, conn):
            thread = _config(case_id)["configurable"]["thread_id"]
            count, stored = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(checkpoint) + LENGTH(metadata)), 0) "
                "FROM checkpoints WHERE thread_id = ?", (thread,)).fetchone()
            writes = conn.execute("SELECT COALESCE(SUM(LENGTH(value)), 0) FROM writes WHERE thread_id = ?",
                                  (thread,)).fetchone()[0]
            values = build(saver).get_state(_config(case_id)).values
        sizes = {k: len(json.dumps(v, default=str)) for k, v in values.items()}
        report[store] = dict(
            checkpoints=count,
            stored_bytes=stored + writes,
            latest_state_bytes=sum(sizes.values()),
            largest_keys=dict(sorted(sizes.items(), key=lambda kv: -kv[1])[:5]),
        )
    return report


# --------------------------------------------------------------------------
# 4. Persisted-memory audit
# --------------------------------------------------------------------------
# Dashed or spaced SSN, or 9 bare digits not inside a longer alphanumeric token
# (so SHA-256 hex digests and long numbers don't match).
_SSN = re.compile(rb"(?<![A-Za-z0-9])(\d{3})[- ]?(\d{2})[- ]?(\d{4})(?![A-Za-z0-9])")
_API_KEY = re.compile(rb"sk-[A-Za-z0-9_\-]{20,}")


def _real_ssns(data: bytes) -> list:
    return [m for m in _SSN.finditer(data) if not 900 <= int(m.group(1)) <= 999]


def _SSN_is_real(data: bytes) -> bool:
    return bool(_real_ssns(data))


def audit_persisted_memory(root) -> dict:
    """Scan every checkpoint, metadata blob and pending write in both stores.
    Test SSNs (900-999) are allowed: the assignment requires them for dependents."""
    root = Path(root)
    findings, scanned = [], 0
    for filename in (INTAKE_DB, WORKFLOW_DB):
        path = root / filename
        if not _has_checkpoints(path):
            continue
        with _readonly_saver(path) as (_, conn):
            rows = list(conn.execute("SELECT thread_id, checkpoint_id, checkpoint, metadata FROM checkpoints"))
            rows += [(t, c, v, b"") for t, c, v in
                     conn.execute("SELECT thread_id, checkpoint_id, value FROM writes")]
        for thread_id, checkpoint_id, *blobs in rows:
            scanned += 1
            data = b"".join(b if isinstance(b, bytes) else str(b).encode() for b in blobs)
            real = _real_ssns(data)
            if real:
                findings.append(dict(store=filename, case_id=thread_id, checkpoint_id=checkpoint_id,
                                     kind="real_looking_ssn", count=len(real)))
            if _API_KEY.search(data):
                findings.append(dict(store=filename, case_id=thread_id, checkpoint_id=checkpoint_id,
                                     kind="api_key"))
    return {"clean": not findings, "records_scanned": scanned, "findings": findings}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect what SilverFile remembers (read-only).")
    parser.add_argument("command", choices=["recap", "timeline", "footprint", "audit"])
    parser.add_argument("--root", default=".", help="Folder containing the session databases.")
    parser.add_argument("--case", help="Case ID (required except for audit).")
    args = parser.parse_args(argv)
    if args.command != "audit" and not args.case:
        parser.error("--case is required for this command")
    if args.command == "recap":
        result = resume_recap(args.root, args.case)
        print(result.get("message") or json.dumps(result, indent=2))
        return 0 if result["found"] else 1
    result = {"timeline": lambda: case_timeline(args.root, args.case),
              "footprint": lambda: memory_footprint(args.root, args.case),
              "audit": lambda: audit_persisted_memory(args.root)}[args.command]()
    print(json.dumps(result, indent=2))
    return 0 if args.command != "audit" or result["clean"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
