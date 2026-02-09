# Codebase Overview

## What Is This?

A **customer support ticket triage system** that classifies issues, retrieves related orders, and drafts intelligent customer responses. This is a Phase 1 mock/demo implementation with static data.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| REST API | FastAPI + Uvicorn |
| Workflow orchestration | LangGraph + LangChain |
| Chat UI | Streamlit |
| Data validation | Pydantic |

## Project Structure

```
app/
├── main.py          # FastAPI REST endpoints (7 routes)
├── graph.py         # LangGraph triage workflow (state machine)
└── chat.py          # Streamlit chat interface
mock_data/
├── orders.json      # 12 sample customer orders
├── issues.json      # 10 keyword-to-issue-type mappings
└── replies.json     # 7 issue-type-to-template reply mappings
interactions/
└── phase1_demo.json # 5 multi-turn demo conversations
```

## Architecture

### Core Workflow (`app/graph.py`)

The triage pipeline is a LangGraph directed acyclic graph with four nodes:

```
ingest → classify_issue → [has order_id?] → fetch_order → draft_reply → END
                                   ↘ (no order) ────────↗
```

1. **Ingest** — Extracts the ticket text and attempts to find an order ID using the regex pattern `ORD\d{4}`.
2. **Classify Issue** — Keyword-matches the ticket text against `issues.json` to determine the issue type (e.g., refund_request, damaged_item, late_delivery).
3. **Fetch Order** (conditional) — If an order ID was found, looks up order details from `orders.json` via a LangChain `@tool`-decorated function and `ToolNode`.
4. **Draft Reply** — Renders a templated customer response from `replies.json` with `{{customer_name}}` and `{{order_id}}` substitution, and provides a recommendation for the support team.

### State Definition

The workflow uses a `TriageState` TypedDict containing:
- `messages` — Conversation history (with LangChain's `add_messages` reducer)
- `ticket_text` — The customer's issue description
- `order_id` — Extracted or provided order ID
- `issue_type` — Classified issue category
- `evidence` — Why it was classified that way
- `recommendation` — Suggested action for the support team

### API Endpoints (`app/main.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/orders/get` | Fetch a single order by ID |
| GET | `/orders/search` | Search orders by email or keyword |
| POST | `/classify/issue` | Classify ticket text into an issue type |
| POST | `/reply/draft` | Generate a templated reply |
| POST | `/triage/invoke` | Full triage pipeline (simple sequential) |
| POST | `/triage/graph` | Full triage using LangGraph workflow |

### Chat Interface (`app/chat.py`)

A Streamlit web app that provides:
- Conversational interface for submitting support tickets
- Sidebar with sample order IDs and example prompts
- Real-time display of issue classification, order details, recommendations, and draft replies

## Mock Data

All data is static JSON — no database or external services.

- **orders.json** — 12 orders with fields: order_id, customer_name, email, items, status, delivery_date, total_amount
- **issues.json** — 10 issue types mapped to keyword lists for classification
- **replies.json** — 7 templated response strings keyed by issue type

## Running the Application

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload       # Start the REST API
streamlit run app/chat.py           # Start the chat UI
python -m app.graph                 # Run CLI test samples
```

## Design Decisions

- **Keyword matching over ML** — Simple substring/regex classification is sufficient for Phase 1.
- **Mock-first** — All data is hardcoded JSON to enable rapid prototyping without infrastructure.
- **Graph-based workflow** — LangGraph enables future complexity (multi-turn context, branching, human-in-the-loop) even though Phase 1 is linear.
- **Multi-UI** — The same business logic in `graph.py` is consumed by both the REST API and the Streamlit chat, keeping concerns separated.
- **Stateless processing** — Each triage request is independent; no session persistence.

## Testing

There are currently no automated tests. Manual testing is done via:
- CLI samples in `graph.py`'s `__main__` block
- Demo conversations in `interactions/phase1_demo.json`
