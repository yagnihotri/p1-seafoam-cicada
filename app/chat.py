"""
Streamlit chat interface for the LangGraph ticket-triage workflow.

Run:  streamlit run app/chat.py
"""

import streamlit as st
from app.graph import run_triage, ORDERS

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ticket Triage Chat", page_icon="🎫", layout="centered")
st.title("Ticket Triage Chat")
st.caption("Describe your issue with an order and the triage agent will classify it, "
           "look up your order, and draft a reply.")

# ── Sidebar: quick-pick an order ────────────────────────────────────────────
with st.sidebar:
    st.header("Quick reference")
    st.markdown("**Sample order IDs you can mention:**")
    for o in ORDERS[:6]:
        st.code(f"{o['order_id']}  {o['customer_name']}", language=None)
    st.markdown("---")
    st.markdown("**Try saying:**")
    st.markdown(
        "- *My order ORD1001 arrived broken*\n"
        "- *I want a refund for ORD1004*\n"
        "- *ORD1002 has not arrived yet*\n"
        "- *Wrong item shipped for ORD1006*"
    )

# ── Session state for chat history ──────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant",
         "content": "Hi! I'm the support triage agent. "
                    "Tell me about your issue and include your order ID "
                    "(e.g. ORD1001) and I'll help you out."}
    ]

# ── Render existing messages ────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Handle new user input ──────────────────────────────────────────────────
if prompt := st.chat_input("Describe your issue..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Run the LangGraph triage
    with st.chat_message("assistant"):
        with st.spinner("Running triage..."):
            result = run_triage(prompt)

        if result.get("error"):
            response = (f"**Could not process your request:** {result['error']}\n\n"
                        "Please include a valid order ID (e.g. ORD1001) in your message.")
            st.markdown(response)
        else:
            order = result.get("order") or {}
            issue = result.get("issue_type", "unknown")
            evidence = result.get("evidence", "")
            recommendation = result.get("recommendation", "")
            reply = result.get("reply_text", "")

            lines = []
            lines.append(f"**Issue classified:** `{issue}`")
            lines.append(f"**Evidence:** {evidence}")
            lines.append("")
            if result.get("order_id"):
                lines.append(f"**Order:** {result['order_id']} — "
                             f"{order.get('customer_name', '')} — "
                             f"*{order.get('status', '')}*")
                if order.get("items"):
                    items_str = ", ".join(
                        f"{i['name']} (x{i['quantity']})" for i in order["items"]
                    )
                    lines.append(f"**Items:** {items_str}")
            else:
                lines.append("**Order:** N/A — no order ID found in message")
            lines.append("")
            lines.append(f"**Recommendation:** {recommendation}")
            lines.append("")
            lines.append("---")
            lines.append("**Draft reply to customer:**")
            lines.append(f"> {reply}")

            response = "\n".join(lines)
            st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
