"""
Minimal LangGraph ticket-triage workflow.

Graph: classify_ticket → fetch_order → draft_reply
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

# ── Load mock data (same files the FastAPI app uses) ────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOCK_DIR = os.path.join(ROOT, "mock_data")


def _load(name: str) -> Any:
    with open(os.path.join(MOCK_DIR, name), encoding="utf-8") as f:
        return json.load(f)


ORDERS = _load("orders.json")
ISSUES = _load("issues.json")
REPLIES = _load("replies.json")


# ── State shared across every node ──────────────────────────────────────────
class TriageState(TypedDict, total=False):
    ticket_text: str
    order_id: str | None
    issue_type: str | None
    confidence: float
    order: dict | None
    reply_text: str | None
    error: str | None


# ── Node 1: classify the ticket ────────────────────────────────────────────
def classify_ticket(state: TriageState) -> TriageState:
    text = state["ticket_text"].lower()
    for rule in ISSUES:
        if rule["keyword"] in text:
            return {"issue_type": rule["issue_type"], "confidence": 0.85}
    return {"issue_type": "unknown", "confidence": 0.1}


# ── Node 2: extract / look-up the order ─────────────────────────────────────
def fetch_order(state: TriageState) -> TriageState:
    order_id = state.get("order_id")
    if not order_id:
        m = re.search(r"(ORD\d{4})", state["ticket_text"], re.IGNORECASE)
        if m:
            order_id = m.group(1).upper()
    if not order_id:
        return {"error": "order_id missing and not found in text"}
    order = next((o for o in ORDERS if o["order_id"] == order_id), None)
    if not order:
        return {"error": f"order {order_id} not found"}
    return {"order_id": order_id, "order": order}


# ── Node 3: draft a reply using the template ────────────────────────────────
def draft_reply(state: TriageState) -> TriageState:
    if state.get("error"):
        return {}
    issue_type = state.get("issue_type", "unknown")
    order = state.get("order") or {}
    template = next(
        (r["template"] for r in REPLIES if r["issue_type"] == issue_type),
        "Hi {{customer_name}}, we are reviewing order {{order_id}}.",
    )
    reply = template.replace(
        "{{customer_name}}", order.get("customer_name", "Customer")
    ).replace("{{order_id}}", order.get("order_id", ""))
    return {"reply_text": reply}


# ── Assemble the graph ──────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    g = StateGraph(TriageState)
    g.add_node("classify_ticket", classify_ticket)
    g.add_node("fetch_order", fetch_order)
    g.add_node("draft_reply", draft_reply)

    g.set_entry_point("classify_ticket")
    g.add_edge("classify_ticket", "fetch_order")
    g.add_edge("fetch_order", "draft_reply")
    g.add_edge("draft_reply", END)
    return g


triage_graph = build_graph().compile()


# ── Convenience runner ──────────────────────────────────────────────────────
def run_triage(ticket_text: str, order_id: str | None = None) -> dict:
    result = triage_graph.invoke(
        {"ticket_text": ticket_text, "order_id": order_id}
    )
    return dict(result)


# ── CLI quick-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = "Hi, my order ORD1001 arrived broken. I need help."
    print("── Triage Graph Demo ──")
    print(f"Input: {sample}\n")
    out = run_triage(sample)
    for k, v in out.items():
        print(f"  {k}: {v}")
