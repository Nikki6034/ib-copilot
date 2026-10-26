"""Recruiting Readiness Score — a single tracked metric from real app data.

Combines three measured components (never invented):
  - Interview performance: average practice score.
  - Topic coverage: how many of the core areas you've practiced.
  - Networking activity: contacts logged, meetings captured, and upcoming recruiting events.
Returns the blended score, the component breakdown, a level label, and the single
highest-leverage next action.
"""

from __future__ import annotations

from . import db

CORE_TOPICS = ["accounting", "valuation", "dcf", "ma", "lbo", "fig", "debt_equity", "behavioral"]
WEIGHTS = {"interview": 0.45, "coverage": 0.25, "networking": 0.30}


def _clamp(v):
    return max(0, min(100, round(v)))


def compute() -> dict:
    practice = db.list_practice(10000)
    scored = [p["score"] for p in practice if p.get("score") is not None]
    interview = round(sum(scored) / len(scored)) if scored else 0

    topics_done = {p["topic"] for p in practice if p.get("score") is not None}
    coverage = _clamp(100 * len(topics_done & set(CORE_TOPICS)) / len(CORE_TOPICS))

    contacts = db.list_contacts()
    meetings = sum(len(db.meetings_for(c["id"])) for c in contacts)
    upcoming = [e for e in db.list_events(upcoming_only=True) if e.get("kind") == "recruiting"]
    networking = _clamp(len(contacts) * 12 + meetings * 18 + min(len(upcoming), 10) * 3)

    comps = {"interview": interview, "coverage": coverage, "networking": networking}
    overall = _clamp(sum(comps[k] * WEIGHTS[k] for k in comps))
    level = ("Interview-ready" if overall >= 70 else "Building momentum" if overall >= 40
             else "Getting started")

    # Highest-leverage next action = weakest component.
    weakest = min(comps, key=lambda k: comps[k])
    next_action = {
        "interview": "Run a few mock interviews — your average score is the biggest lever.",
        "coverage": f"Practice a topic you haven't yet: {_missing_topic(topics_done)}.",
        "networking": "Log a banker contact and your meeting notes to track follow-ups.",
    }[weakest]

    return {
        "score": overall,
        "level": level,
        "components": comps,
        "weights": WEIGHTS,
        "detail": {
            "practice_sessions": len(scored),
            "topics_covered": sorted(topics_done & set(CORE_TOPICS)),
            "contacts": len(contacts),
            "meetings_logged": meetings,
            "upcoming_recruiting": len(upcoming),
        },
        "next_action": next_action,
        "basis": "All components are measured from your own app activity (not estimates).",
    }


def _missing_topic(done: set) -> str:
    labels = {"accounting": "Accounting", "valuation": "Valuation", "dcf": "DCF", "ma": "M&A",
              "lbo": "LBO", "fig": "FIG", "debt_equity": "Debt & Equity", "behavioral": "Behavioral"}
    for t in CORE_TOPICS:
        if t not in done:
            return labels[t]
    return "a new area"
