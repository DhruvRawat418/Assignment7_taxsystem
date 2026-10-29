"""Standalone Intake demo: talk to the Intake agent in the terminal.

    python -m demo.run_intake                  # offline rule parser
    SILVERFILE_MODEL=openai:gpt-4o-mini python -m demo.run_intake   # real LLM parser
    python -m demo.run_intake --handoff maria  # send a finished interview through the team graph

Sessions are saved in intake_sessions.db: quit with Ctrl+C on Tuesday, run again
on Friday with the same session name, and it picks up where you left off. The
session name is also the team case id.

The human_review node here stands in for the dashboard while the taxpayer is
still being interviewed. Once the interview is done, the team orchestrator takes
over through make_intake_provider (src/agents/intake_contract.py).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.agents.intake import (
    IntakeState, initial_intake_state, make_intake_node, now_iso, pending_hitl, provenance, summarize,
)
from src.agents.intake_contract import make_intake_provider, not_ready_reason, sqlite_sessions, to_packet
from src.agents.intake_parser import LLMParser, RuleParser

DB = "intake_sessions.db"


def human_review(state: dict) -> dict:
    """Kushim staff resolve an escalation. Answer = {"id", "resolution", "staff", "resume", "updates"}."""
    req = pending_hitl(state)[0]
    decision = interrupt({"type": "escalation", "request": req, "covered_so_far": summarize(state)})
    upd: dict = {"hitl_resolutions": [{"id": req["id"], "resolution": decision["resolution"],
                                        "staff": decision["staff"], "at": now_iso()}]}
    if decision.get("updates"):
        upd["answers"] = {f: provenance(v, "set during human review", f"Kushim staff: {decision['staff']}")
                          for f, v in decision["updates"].items()}
    if decision.get("resume", True):
        upd["intake_paused"] = False
        upd["preface"] = "A member of our team has looked at this. Let's continue."
    return upd


def route(state: dict) -> str:
    if pending_hitl(state):
        return "human_review"
    if state.get("intake_complete") or state.get("intake_paused"):
        return END
    return "intake"


def build_graph(parser, checkpointer):
    g = StateGraph(IntakeState)
    g.add_node("intake", make_intake_node(parser))
    g.add_node("human_review", human_review)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", route, ["intake", "human_review", END])
    g.add_conditional_edges("human_review", route, ["intake", "human_review", END])
    return g.compile(checkpointer=checkpointer)


def current_interrupt(graph, config):
    snap = graph.get_state(config)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


async def handoff(case_id, stop=False):
    """Start a case, or display its previously saved progress."""
    from pathlib import Path
    from langgraph.types import Command
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from src.agents.openai_transport import openai_review_call
    from src.agents.adversarial import make_adversarial_provider
    from src.agents.eligibility import make_eligibility_node
    from src.integration.contracts import Providers
    from src.integration.graph import build_graph as build_team_graph
    from src.integration.state import new_case

    providers = Providers(
        intake=make_intake_provider(sqlite_sessions(DB)),
        rules=make_eligibility_node(),
        adversarial=make_adversarial_provider(openai_review_call),
    )

    project_root = Path(__file__).resolve().parents[1]
    database = str(project_root / "workflow_sessions.db")
    config = {"configurable": {"thread_id": case_id}}

    async with AsyncSqliteSaver.from_conn_string(database) as saver:
        team = build_team_graph(providers, checkpointer=saver)

        snapshot = await team.aget_state(config)
        loaded_saved_case = bool(snapshot.values)
        if stop:
            has_pending_review = any(
                task.interrupts for task in snapshot.tasks
            )

            if not has_pending_review:
                return {
                    "status": "action_not_available",
                    "message": "This case has no pending human review.",
                }

            await team.ainvoke(
                Command(resume={"action": "stop"}),
                config,
            )
            snapshot = await team.aget_state(config)

        if not loaded_saved_case:
            await team.ainvoke(new_case(case_id), config)
            snapshot = await team.aget_state(config)

        state = snapshot.values

        pending_reviews = [
            interruption.value
            for task in snapshot.tasks
            for interruption in task.interrupts
        ]

        return {
            "status": (
                "paused_for_human_review"
                if pending_reviews
                else state["status"]
            ),
            "loaded_saved_case": loaded_saved_case,
            "issues": state.get("issues", []),
            "pending_reviews": pending_reviews,
            "stages": [
                event["stage"]
                for event in state.get("events", [])
            ],
        }

def main():
    args = argparse.ArgumentParser(description="SilverFile Intake demo")
    args.add_argument("--handoff", metavar="SESSION", help="run the team graph on a finished interview")
    args.add_argument(
        "--stop",
        action="store_true",
        help="Stop the saved case specified with --handoff.",
    )
    args = args.parse_args()
    if args.stop and not args.handoff:
        raise SystemExit("--stop requires --handoff SESSION")
    if args.handoff:
        print(json.dumps(
            asyncio.run(handoff(args.handoff, stop=args.stop)),
            indent=2,
        ))
        return

    parser = LLMParser() if os.getenv("SILVERFILE_MODEL") else RuleParser()
    conn = sqlite3.connect(DB, check_same_thread=False)
    graph = build_graph(parser, SqliteSaver(conn))
    session = input("Session name (letters, digits, - or _): ").strip() or "demo"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session):
        print("Please use only letters, digits, - or _ (this name becomes the case id).")
        return
    config = {"configurable": {"thread_id": session}}

    if current_interrupt(graph, config):
        recap = summarize(graph.get_state(config).values)
        print("\nWelcome back. Here is what we covered so far:\n" + (recap or "- nothing yet") + "\n")
    else:
        graph.invoke(initial_intake_state(), config)

    while (payload := current_interrupt(graph, config)) is not None:
        if payload["type"] == "ask_user":
            if payload["message"]:
                print(f"\n{payload['message']}")
            reply = input(f"{payload['question']}\n> ")
            graph.invoke(Command(resume=reply), config)
        else:
            r = payload["request"]
            print(f"\n=== KUSHIM STAFF: escalation {r['id']} ===\nReason: {r['reason']}\nDetail: {r['detail']}")
            staff = input("Your name: ")
            resolution = input("Resolution note: ")
            updates = {}
            if r["reason"] == "filing_status_ambiguity":
                fs = input("Set filing status (single / married_filing_jointly / qualifying_surviving_spouse): ")
                updates = {"filing_status": fs.strip()} if fs.strip() else {}
            resume = input("Resume the interview? (y/n): ").lower().startswith("y")
            graph.invoke(Command(resume={"resolution": resolution, "staff": staff,
                                         "resume": resume, "updates": updates}), config)

    final = graph.get_state(config).values
    print(f"\n{final.get('preface', '')}\n\nSummary:\n{summarize(final)}")
    if not_ready_reason(final) is None:
        print(f"\nHandoff packet for the team (run --handoff {session} to send it):")
        print(json.dumps(to_packet(final), indent=2))


if __name__ == "__main__":
    main()
