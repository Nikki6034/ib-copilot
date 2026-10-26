"""Agent B — IB Knowledge & Deal Prep.

Retrieval-augmented: searches the user's guides, answers from relevant excerpts, and
cites the source document + page. Explicitly flags when something cannot be verified from
the sources, and never fabricates quotations, figures, or references.
"""

from __future__ import annotations

from . import base
from .. import rag, sanitize

AGENT = "knowledge"


def _sources(chunks: list[dict]) -> list[dict]:
    return [{"citation": c["citation"], "doc": c["doc"], "page": c["page"], "score": c["score"]} for c in chunks]


def answer(question: str, topic: str | None = None, k: int = 5) -> dict:
    chunks = rag.retriever.retrieve(question, k=k, topic=topic)
    context = sanitize.format_context(chunks)
    grounded = bool(chunks)
    system = (
        "You are the IB Knowledge agent. Answer the user's question using ONLY the "
        "retrieved excerpts when they are relevant. Cite sources inline as [1], [2] matching "
        "the numbered excerpts. If the excerpts do not contain the answer, say: 'I can't "
        "verify this from your uploaded guides,' then you MAY give a brief general-knowledge "
        "answer clearly prefixed with '(General knowledge — not from your guides)'. Keep it "
        "tight and interview-ready."
    )
    user = f"{context}\n\nQUESTION: {sanitize.clean(question)}"
    res = base.run(AGENT, "answer", system, user, detail={"topic": topic, "n_chunks": len(chunks)})
    return {
        "answer": res.text or "(no answer generated)",
        "grounded": grounded,
        "sources": _sources(chunks),
        "provenance": "retrieved" if grounded else "ai_generated",
        "usage": _usage(res),
        "error": res.error,
    }


def terminology(term: str) -> dict:
    chunks = rag.retriever.retrieve(term, k=4)
    context = sanitize.format_context(chunks)
    system = (
        "You are the IB Knowledge agent. Explain the finance term in three labeled parts:\n"
        "1) Plain English — one or two sentences a non-finance person understands.\n"
        "2) IB-level — the precise investment-banking definition, grounded in the excerpts "
        "with [n] citations where possible.\n"
        "3) Example — a short concrete example.\n"
        "If the excerpts don't cover it, still explain from general knowledge but add "
        "'(General knowledge — not from your guides)'."
    )
    user = f"{context}\n\nTERM: {sanitize.clean(term)}"
    res = base.run(AGENT, "terminology", system, user, detail={"term": term})
    return {"term": term, "explanation": res.text, "sources": _sources(chunks),
            "provenance": "retrieved" if chunks else "ai_generated", "usage": _usage(res), "error": res.error}


def flashcards(topic: str, n: int = 6) -> dict:
    chunks = rag.retriever.retrieve(topic.replace("_", " ") + " key concepts interview", k=8, topic=topic)
    context = sanitize.format_context(chunks)
    system = (
        "You are the IB Knowledge agent. From the retrieved excerpts, create concise "
        f"flashcards. Return STRICT JSON: {{\"cards\":[{{\"front\":\"...\",\"back\":\"...\","
        "\"source\":\"<citation or 'general'>\"}}]}}. Base each card on the excerpts; mark "
        "cards not supported by them with source 'general'. No preamble, JSON only."
    )
    user = f"{context}\n\nMake {n} flashcards on: {sanitize.clean(topic)}"
    res = base.run(AGENT, "flashcards", system, user, max_tokens=2000, detail={"topic": topic, "n": n})
    data = base.parse_json(res.text) or {}
    return {"cards": data.get("cards", []), "sources": _sources(chunks),
            "provenance": "retrieved", "usage": _usage(res), "error": res.error}


def quiz(topic: str, n: int = 5) -> dict:
    chunks = rag.retriever.retrieve(topic.replace("_", " ") + " interview questions", k=8, topic=topic)
    context = sanitize.format_context(chunks)
    system = (
        "You are the IB Knowledge agent. From the retrieved excerpts, write quiz questions "
        f"with model answers. Return STRICT JSON: {{\"questions\":[{{\"q\":\"...\","
        "\"a\":\"...\",\"source\":\"<citation>\"}}]}}. JSON only."
    )
    user = f"{context}\n\nWrite {n} quiz questions on: {sanitize.clean(topic)}"
    res = base.run(AGENT, "quiz", system, user, max_tokens=2000, detail={"topic": topic, "n": n})
    data = base.parse_json(res.text) or {}
    return {"questions": data.get("questions", []), "sources": _sources(chunks),
            "provenance": "retrieved", "usage": _usage(res), "error": res.error}


def grade(question: str, reference: str, answer: str) -> dict:
    """Grade a quiz answer against the reference. Returns correct/score/feedback."""
    system = (
        "You are grading a candidate's quiz answer against a reference answer. Be fair but "
        "rigorous. Return STRICT JSON: {\"correct\":true|false,\"score\":0-100,\"feedback\":"
        "\"1-2 sentences: what was right and what was missing\"}. 'correct' is true if the "
        "answer captures the key idea(s) of the reference, even if worded differently. JSON only."
    )
    user = (f"QUESTION: {sanitize.clean(question)}\n\nREFERENCE ANSWER: {sanitize.clean(reference)}\n\n"
            f"{sanitize.wrap_untrusted(answer, 'CANDIDATE ANSWER')}")
    res = base.run(AGENT, "grade", system, user, max_tokens=400)
    data = base.parse_json(res.text) or {}
    return {"correct": bool(data.get("correct")), "score": data.get("score"),
            "feedback": data.get("feedback", ""), "usage": _usage(res), "error": res.error}


def _usage(res) -> dict:
    return {"input_tokens": res.input_tokens, "cached_tokens": res.cached_tokens,
            "output_tokens": res.output_tokens, "cost_usd": res.cost_usd,
            "latency_s": res.latency_s, "model": res.model}
