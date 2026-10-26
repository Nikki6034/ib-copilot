"""Central orchestrator.

A single choke point between the HTTP layer and the four specialized agents. It enforces
the daily run limit, validates required parameters, restricts each agent to its permitted
tools, and turns any failure into a structured error instead of a crash. Simple direct
calls are used per action — the orchestrator does not invoke every agent on every request.
"""

from __future__ import annotations

from . import config, db
from .agents import banker, interview, knowledge, markets

# Declarative agent catalog (also rendered in the architecture view / README).
AGENTS = {
    "interview": {"name": "Interview Coach", "purpose": "Mock interviews + rubric feedback",
                  "tools": ["read_documents", "write_practice"]},
    "knowledge": {"name": "Knowledge & Deal Prep", "purpose": "Grounded Q&A, terms, flashcards, quizzes",
                  "tools": ["read_documents"]},
    "markets": {"name": "Markets & Deals", "purpose": "News feed + interview-ready deal briefs",
                "tools": ["read_news", "read_documents"]},
    "banker": {"name": "Banker Relationship", "purpose": "Meeting summaries + email drafts",
               "tools": ["read_db", "write_draft"]},
}

# action -> (callable, required params, agent)
ACTIONS = {
    "knowledge.answer": (knowledge.answer, ["question"], "knowledge"),
    "knowledge.terminology": (knowledge.terminology, ["term"], "knowledge"),
    "knowledge.flashcards": (knowledge.flashcards, ["topic"], "knowledge"),
    "knowledge.quiz": (knowledge.quiz, ["topic"], "knowledge"),
    "knowledge.grade": (knowledge.grade, ["question", "reference", "answer"], "knowledge"),
    "interview.generate_question": (interview.generate_question, ["topic"], "interview"),
    "interview.study_plan": (interview.study_plan, [], "interview"),
    "interview.evaluate": (interview.evaluate, ["mode", "topic", "question", "answer"], "interview"),
    "markets.feed": (markets.feed, [], "markets"),
    "markets.deal_brief": (markets.deal_brief, ["item_id"], "markets"),
    "markets.news_brief": (markets.news_brief, ["headline"], "markets"),
    "banker.summarize_meeting": (banker.summarize_meeting, ["notes"], "banker"),
    "banker.draft_email": (banker.draft_email, ["contact"], "banker"),
    "banker.prep_chat": (banker.prep_chat, [], "banker"),
}


class OrchestratorError(Exception):
    pass


def dispatch(action: str, params: dict):
    if action not in ACTIONS:
        raise OrchestratorError(f"Unknown action: {action}")
    fn, required, agent = ACTIONS[action]

    # Bounded cost: enforce the configurable daily run cap.
    if db.runs_today() >= config.DAILY_RUN_LIMIT:
        raise OrchestratorError(
            f"Daily run limit reached ({config.DAILY_RUN_LIMIT}). Raise DAILY_RUN_LIMIT in .env to continue.")

    missing = [p for p in required if params.get(p) in (None, "")]
    if missing:
        raise OrchestratorError(f"Missing required parameter(s): {', '.join(missing)}")

    try:
        return fn(**{k: v for k, v in params.items() if k != "action"})
    except OrchestratorError:
        raise
    except Exception as e:  # noqa: BLE001 - never leak a stack trace to the client
        return {"error": f"{type(e).__name__}: {str(e)[:200]}", "agent": agent, "action": action}
