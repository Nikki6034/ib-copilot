"""Agent A — Interview Coach.

Generates practice questions grounded in the user's guides, then evaluates answers against
an explicit rubric. Observable delivery signals (filler words, pace, hedging) are measured
deterministically IN CODE; the model provides rubric judgments separately. The response
clearly separates measured signals from AI judgments and never claims to measure
personality or likeability.
"""

from __future__ import annotations

import re

from . import base
from .. import db, rag, sanitize

AGENT = "interview"

FILLERS = ["um", "uh", "er", "like", "you know", "basically", "actually", "literally",
           "sort of", "kind of", "i mean"]
HEDGES = ["maybe", "i think", "probably", "i guess", "perhaps", "kind of", "sort of",
          "i'm not sure", "possibly"]

TECH_RUBRIC = ["technical_accuracy", "structure", "relevance", "conciseness", "use_of_examples", "clarity"]
BEHAVIORAL_RUBRIC = ["situation", "task", "action", "result", "conciseness", "clarity"]

BEHAVIORAL_PROMPTS = {
    "tell_me_about_yourself": "Tell me about yourself.",
    "why_ib": "Why investment banking?",
    "why_fig": "Why the Financial Institutions Group (FIG)?",
    "why_ma": "Why M&A?",
    "leadership": "Tell me about a time you led a team.",
    "failure": "Tell me about a time you failed.",
    "conflict": "Tell me about a time you had a conflict with a teammate.",
    "teamwork": "Tell me about a time you worked on a team to achieve a goal.",
    "strength_weakness": "What is your greatest strength and weakness?",
}


def generate_question(topic: str, difficulty: str = "medium", mode: str = "technical") -> dict:
    if mode == "behavioral" and topic in BEHAVIORAL_PROMPTS:
        return {"question": BEHAVIORAL_PROMPTS[topic], "source": "Standard behavioral set",
                "provenance": "curated", "mode": mode, "topic": topic, "difficulty": difficulty}
    chunks = rag.retriever.retrieve(f"{topic.replace('_',' ')} interview question", k=6, topic=topic)
    context = sanitize.format_context(chunks)
    system = (
        "You are the Interview Coach. From the retrieved excerpts, produce ONE realistic "
        f"interview question at '{difficulty}' difficulty. Prefer a question actually present "
        "in the excerpts. Return STRICT JSON: {\"question\":\"...\",\"source\":\"<citation or "
        "'general'>\"}. JSON only."
    )
    user = f"{context}\n\nTopic: {sanitize.clean(topic)} | difficulty: {difficulty}"
    res = base.run(AGENT, "generate_question", system, user, max_tokens=500,
                   detail={"topic": topic, "difficulty": difficulty, "mode": mode})
    data = base.parse_json(res.text) or {}
    return {"question": data.get("question") or res.text.strip(),
            "source": data.get("source", "general"),
            "provenance": "retrieved" if chunks else "ai_generated",
            "mode": mode, "topic": topic, "difficulty": difficulty, "error": res.error}


def _count_phrases(low: str, phrases: list[str]) -> int:
    """Count whole-word / whole-phrase occurrences (not substrings inside words)."""
    total = 0
    for p in phrases:
        total += len(re.findall(r"(?<!\w)" + re.escape(p) + r"(?!\w)", low))
    return total


def study_plan() -> dict:
    """Generate a 7-day prep plan tailored to the student's MEASURED performance."""
    from .. import db, readiness
    r = readiness.compute()
    weak = db.topic_averages()
    upcoming = [e for e in db.list_events(upcoming_only=True) if e.get("kind") == "recruiting"][:8]
    weak_txt = ", ".join(f"{w['topic']} (avg {w['avg_score']})" for w in weak) or "none practiced yet"
    cov = ", ".join(r["detail"]["topics_covered"]) or "none yet"
    events_txt = "; ".join(f"{e['start']} {e['title']}" for e in upcoming) or "none on calendar"
    system = (
        "You are an IB recruiting coach. Build a focused, realistic 7-day prep plan (about "
        "45-60 minutes/day) tailored to this student's MEASURED performance. Return markdown "
        "with one '### Day N' header per day; under each, 2-3 concrete tasks as '- ' bullets "
        "(e.g. drill a specific weak topic with N practice questions, prep a specific upcoming "
        "coffee chat, review the featured deal, do flashcards). Prioritize the weakest topics "
        "and any upcoming recruiting events. Be specific and encouraging; no preamble."
    )
    user = (f"Readiness score: {r['score']}/100 ({r['level']}).\n"
            f"Component scores — interview {r['components']['interview']}, coverage "
            f"{r['components']['coverage']}, networking {r['components']['networking']}.\n"
            f"Weak topics (lowest first): {weak_txt}.\nTopics already practiced: {cov}.\n"
            f"Upcoming recruiting events: {events_txt}.\n"
            f"Practice sessions so far: {r['detail']['practice_sessions']}.")
    res = base.run(AGENT, "study_plan", system, user, max_tokens=1600)
    return {"plan": res.text, "readiness": r["score"], "level": r["level"],
            "usage": {"input_tokens": res.input_tokens, "cached_tokens": res.cached_tokens,
                      "output_tokens": res.output_tokens, "cost_usd": res.cost_usd,
                      "latency_s": res.latency_s, "model": res.model}, "error": res.error}


def _measured_signals(answer: str, duration_seconds: float | None) -> dict:
    low = answer.lower()
    words = re.findall(r"[a-z']+", low)
    wc = len(words)
    filler = _count_phrases(low, FILLERS)
    hedge = _count_phrases(low, HEDGES)
    out = {
        "word_count": wc,
        "filler_word_count": filler,
        "hedging_phrase_count": hedge,
        "measured": True,
    }
    if duration_seconds and duration_seconds > 0:
        out["duration_seconds"] = round(duration_seconds, 1)
        out["words_per_minute"] = round(wc / (duration_seconds / 60), 1)
    else:
        out["words_per_minute"] = None  # no timing captured
    return out


def evaluate(mode: str, topic: str, question: str, answer: str,
             duration_seconds: float | None = None) -> dict:
    rubric = BEHAVIORAL_RUBRIC if mode == "behavioral" else TECH_RUBRIC
    signals = _measured_signals(answer, duration_seconds)

    # Ground technical evaluation in the guides (so feedback reflects real IB answers).
    chunks = rag.retriever.retrieve(f"{topic.replace('_',' ')} {question}", k=4,
                                    topic=None if mode == "behavioral" else topic)
    context = sanitize.format_context(chunks) if mode != "behavioral" else "(behavioral — judge on structure, not retrieved facts)"
    framework = ("STAR (Situation, Task, Action, Result)" if mode == "behavioral"
                 else "technical correctness grounded in the excerpts")
    system = (
        "You are the Interview Coach. Score the candidate's answer against an EXPLICIT rubric. "
        f"Rubric dimensions (each scored 1-5 with a one-line comment): {rubric}. "
        f"Judge using the {framework}. These are SUBJECTIVE AI judgments, not measurements. "
        "Do NOT comment on personality, likeability, or delivery metrics (those are measured "
        "separately in code). Return STRICT JSON: {\"scores\":{<dim>:{\"score\":n,\"comment\":"
        "\"..\"}},\"overall\":<0-100>,\"strengths\":[..],\"missing\":[..],\"improved_outline\":"
        "\"..\",\"followups\":[..],\"confidence\":{\"score\":<0-100>,\"evidence\":\"what in the "
        "answer supports this, citing [n] where relevant\"}}. JSON only."
    )
    user = (f"{context}\n\nMODE: {mode}\nQUESTION: {sanitize.clean(question)}\n\n"
            f"{sanitize.wrap_untrusted(answer, 'CANDIDATE ANSWER')}")
    res = base.run(AGENT, "evaluate", system, user, max_tokens=1800,
                   detail={"mode": mode, "topic": topic})
    data = base.parse_json(res.text) or {}
    overall = data.get("overall")
    try:
        overall = int(overall)
    except (TypeError, ValueError):
        overall = None

    db.add_practice(mode=mode, topic=topic, question=question, answer=answer,
                    score=overall, rubric=data.get("scores"),
                    feedback=data.get("improved_outline"))

    return {
        "measured_signals": signals,                       # objective, computed in code
        "rubric_scores": data.get("scores", {}),           # subjective AI judgment
        "overall_score": overall,
        "strengths": data.get("strengths", []),
        "missing": data.get("missing", []),
        "improved_outline": data.get("improved_outline", ""),
        "followups": data.get("followups", []),
        "confidence": data.get("confidence", {}),
        "sources": [{"citation": c["citation"]} for c in chunks],
        "disclaimer": "Rubric scores and confidence are AI judgments. Only the 'measured_signals' "
                      "are objectively computed. No personality or likeability is inferred.",
        "usage": {"input_tokens": res.input_tokens, "cached_tokens": res.cached_tokens,
                  "output_tokens": res.output_tokens, "cost_usd": res.cost_usd,
                  "latency_s": res.latency_s, "model": res.model},
        "error": res.error,
    }
