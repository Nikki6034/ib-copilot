# IB Copilot

An AI recruiting copilot for an MBA student recruiting for **Investment Banking**, focused on
the **Financial Institutions Group (FIG)** and **M&A**. It turns scattered prep — interview
practice, technical knowledge, deal study, and banker networking — into one connected
workflow, grounded in your own prep documents and your real recruiting calendar.

> **Model:** `gpt-6-luna` via the Portkey gateway (course key). All model calls and secrets
> stay on the server; nothing sensitive is exposed to the browser.

## What it does

Four specialized agents behind a single orchestrator:

| Agent | What it does | Tools |
|---|---|---|
| **A · Interview Coach** | Mock interviews (technical + behavioral/TMAT). Measures delivery (filler words, pace, hedging) **in code**, scores answers on an explicit **rubric** via the model, and generates a **7-day plan** from your performance. Voice read-aloud + spoken answers. | document retrieval, practice log |
| **B · Knowledge & Deals** | Grounded Q&A, plain-English → IB-level term explanations, **flip-card flashcards** (with voice), and an **interactive, AI-graded quiz**. Every answer cites the source doc + page. | document retrieval |
| **C · Deals** | Interview-ready deal briefs grounded in your own deal documents (e.g. a FIG M&A walkthrough), plus a "practice this deal" drill. | document retrieval |
| **D · Banker Relationship** | Contacts, meeting notes → summaries, **one-click chat prep** (tailored questions to ask + likely questions back + opener), and thank-you email drafts exported as `.eml`. **Never sends anything.** | database, draft writer |

Standout features: a **Recruiting Readiness Score** (measured from your activity), **one-click
chat prep** off your calendar, **deal-to-interview drills**, and a **performance-based 7-day plan**.

## Architecture

```
Browser (no secrets)
        │  JSON
        ▼
   FastAPI  ──►  Orchestrator  ──►  Agent A / B / C / D
                 (tool allowlist,      │
                  usage cap,           ├─► RAG (BM25 over your guides, cited)
                  arg validation)      ├─► SQLite (contacts, meetings, drafts, practice, events, run log)
                                       └─► LLM client → Portkey → gpt-6-luna
```
See `docs/report.html` for the full diagram, a traced run, token costs, and safety evidence.

## Prerequisites
- Python 3.11+ (developed on 3.14)
- A `PORTKEY_API_KEY` (course key) — or set `USE_DIRECT_OPENAI=1` with your own `OPENAI_API_KEY`.

## Install & run (fresh clone)

```bash
cd "IB Copilot"
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # then add your key (see below)
python -m uvicorn server.main:app --port 8000
```

Open **http://localhost:8000**. The retrieval index builds automatically on first run.

### Environment variables

The app looks for `.env` in the **project root first, then one directory above it** (the
teaching-staff layout). List every key in `.env.example`; never commit a real `.env`.

| Variable | Required | Purpose |
|---|---|---|
| `PORTKEY_API_KEY` | yes (course mode) | course model access via Portkey |
| `PORTKEY_BASE_URL` | no | defaults to `https://api.portkey.ai/v1` |
| `OPENAI_MODEL` | no | defaults to `gpt-6-luna` |
| `OPENAI_API_KEY` | only if `USE_DIRECT_OPENAI=1` | use your own OpenAI key/model instead |

## How to test

```bash
python -m server.ingest          # (re)build the retrieval index
python -m uvicorn server.main:app --port 8000
```
Then in the app: ask a question (Knowledge), run a mock interview (Interview Coach), review
the featured deal (Deals), generate chat prep from a calendar event (Bankers & Calendar),
check real token costs (Diagnostics → Tokenomics), and run the prompt-injection test
(Diagnostics → Safety). A repeatable safety test is also runnable headless:

```bash
python -c "from server.safety_test import run_safety_test; import json; print(json.dumps(run_safety_test(), indent=2))"
```

## Data & the test dataset
The repo ships a small **original** test dataset so it runs on a fresh clone: `data/guides/`
contains original topic primers (accounting, valuation, M&A/LBO/FIG) plus an example deal
walkthrough. **Purchased/copyrighted prep guides are git-ignored and not distributed** — drop
your own licensed PDFs into `data/guides/` locally for full coverage; they are indexed
automatically. Calendar import accepts an Outlook `.ics` export or a month-view print-to-PDF
(recruiting events only).

## Optional integrations
- **Outlook:** local-only by design — import an `.ics`/PDF calendar; drafts export as `.eml`.
  No OAuth, no mailbox access, nothing sent. (A live Microsoft Graph integration could be
  added with least-privilege read + draft scopes.)
- **News:** no live news feed is included (it was removed for reliability); Deals is grounded
  in your own documents. A news API could be plugged into Agent C.

## Known limitations
- Retrieval is lexical (BM25), not embeddings — the course key doesn't expose embeddings.
- Outlook month-PDF import can truncate long event titles (an `.ics` export avoids this).
- Rubric scores and the readiness score are AI/heuristic judgments; measured delivery signals
  and token costs are objective.
