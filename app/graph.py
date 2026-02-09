"""
LangGraph ticket-triage workflow.

Nodes:  ingest → classify_issue → fetch_order (ToolNode) → draft_reply
State:  messages, ticket_text, order_id, issue_type, evidence, recommendation
"""

from __future__ import annotations

import json
import os
import re
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

# ── Load mock data ──────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOCK_DIR = os.path.join(ROOT, "mock_data")


def _load(name: str) -> Any:
    with open(os.path.join(MOCK_DIR, name), encoding="utf-8") as f:
        return json.load(f)


ORDERS = _load("orders.json")
ISSUES = _load("issues.json")
REPLIES = _load("replies.json")

RECOMMENDATIONS = {
    "refund_request": "Process refund for the customer",
    "damaged_item": "Send replacement item to customer",
    "late_delivery": "Track package and provide updated ETA",
    "missing_item": "Investigate and ship missing item",
    "duplicate_charge": "Refund the duplicate charge",
    "wrong_item": "Arrange return and send correct item",
    "defective_product": "Honor warranty and replace product",
    "unknown": "Escalate to human agent for review",
}


# ── State ───────────────────────────────────────────────────────────────────
class TriageState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    ticket_text: str
    order_id: str | None
    issue_type: str | None
    evidence: str | None
    recommendation: str | None


# ── Tool: fetch_order ───────────────────────────────────────────────────────
@tool
def fetch_order_tool(order_id: str) -> dict:
    """Look up a customer order by its order ID (e.g. ORD1001)."""
    order = next((o for o in ORDERS if o["order_id"] == order_id), None)
    if not order:
        return {"error": f"Order {order_id} not found"}
    return order


# ── Node 1: ingest ──────────────────────────────────────────────────────────
def ingest(state: TriageState) -> dict:
    """Extract ticket_text from the latest message and attempt to find order_id."""
    last_msg = state["messages"][-1]
    ticket_text = last_msg.content

    # Control flow: extract order_id if missing
    order_id = state.get("order_id")
    if not order_id:
        m = re.search(r"(ORD\d{4})", ticket_text, re.IGNORECASE)
        if m:
            order_id = m.group(1).upper()

    return {"ticket_text": ticket_text, "order_id": order_id}


# ── Node 2: classify_issue ─────────────────────────────────────────────────
def classify_issue(state: TriageState) -> dict:
    """Keyword-match the ticket text and set issue_type + evidence."""
    text = state["ticket_text"].lower()

    for rule in ISSUES:
        if rule["keyword"] in text:
            issue_type = rule["issue_type"]
            evidence = f"Matched keyword '{rule['keyword']}' in ticket text"
            break
    else:
        issue_type = "unknown"
        evidence = "No matching keywords found in ticket text"

    order_id = state.get("order_id")
    if order_id:
        # Create an AIMessage with a tool_call so the ToolNode fires
        tool_msg = AIMessage(
            content=f"Classified as {issue_type}. Looking up order {order_id}...",
            tool_calls=[{
                "id": "fetch_order_call",
                "name": "fetch_order_tool",
                "args": {"order_id": order_id},
            }],
        )
        return {"issue_type": issue_type, "evidence": evidence, "messages": [tool_msg]}

    # No order_id — skip tool call
    msg = AIMessage(content=f"Classified as {issue_type}. No order ID found to look up.")
    return {"issue_type": issue_type, "evidence": evidence, "messages": [msg]}


# ── Node 3: fetch_order (ToolNode) ──────────────────────────────────────────
fetch_order = ToolNode([fetch_order_tool])


# ── Node 4: draft_reply ────────────────────────────────────────────────────
def draft_reply(state: TriageState) -> dict:
    """Build a customer reply from the template and set recommendation."""
    issue_type = state.get("issue_type", "unknown")

    # Pull order data from the ToolMessage (if the tool ran)
    order = {}
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            try:
                order = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            except (json.JSONDecodeError, TypeError):
                order = {}
            break

    template = next(
        (r["template"] for r in REPLIES if r["issue_type"] == issue_type),
        "Hi {{customer_name}}, we are reviewing order {{order_id}}.",
    )
    reply = template.replace(
        "{{customer_name}}", order.get("customer_name", "Customer")
    ).replace("{{order_id}}", order.get("order_id", state.get("order_id") or ""))

    recommendation = RECOMMENDATIONS.get(issue_type, RECOMMENDATIONS["unknown"])
    response = AIMessage(content=reply)

    return {"recommendation": recommendation, "messages": [response]}


# ── Conditional edge: should we call the tool? ──────────────────────────────
def route_after_classify(state: TriageState) -> str:
    """If order_id exists, route to fetch_order ToolNode; otherwise skip to draft_reply."""
    if state.get("order_id"):
        return "fetch_order"
    return "draft_reply"


# ── Assemble the graph ──────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    g = StateGraph(TriageState)

    g.add_node("ingest", ingest)
    g.add_node("classify_issue", classify_issue)
    g.add_node("fetch_order", fetch_order)
    g.add_node("draft_reply", draft_reply)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "classify_issue")
    g.add_conditional_edges("classify_issue", route_after_classify)
    g.add_edge("fetch_order", "draft_reply")
    g.add_edge("draft_reply", END)

    return g


triage_graph = build_graph().compile()


# ── Convenience runner ──────────────────────────────────────────────────────
def run_triage(ticket_text: str, order_id: str | None = None) -> dict:
    """Run the triage graph and return a clean dict of results."""
    initial_state: dict = {
        "messages": [HumanMessage(content=ticket_text)],
    }
    if order_id:
        initial_state["order_id"] = order_id

    result = triage_graph.invoke(initial_state)

    # Extract order from ToolMessage if present
    order = {}
    for msg in reversed(result["messages"]):
        if isinstance(msg, ToolMessage):
            try:
                order = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            except (json.JSONDecodeError, TypeError):
                order = {}
            break

    return {
        "order_id": result.get("order_id"),
        "issue_type": result.get("issue_type"),
        "evidence": result.get("evidence"),
        "recommendation": result.get("recommendation"),
        "order": order if order and "error" not in order else None,
        "reply_text": result["messages"][-1].content,
        "error": order.get("error") if isinstance(order, dict) and "error" in order else None,
    }


# ── CLI quick-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        "Hi, my order ORD1001 arrived broken. I need help.",
        "I want a refund for ORD1004.",
        "My package is late, no idea what my order number is.",
    ]
    for sample in samples:
        print(f"── Input: {sample}")
        out = run_triage(sample)
        for k, v in out.items():
            print(f"   {k}: {v}")
        print()
