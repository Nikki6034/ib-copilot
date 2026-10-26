"""Agent C — Markets & Deals.

Serves a LIVE, dated, source-linked IB/FIG/M&A news feed (free Google News RSS, no key)
and generates interview-ready briefs. The featured deal is the user's own uploaded
Santander/Webster walkthrough, and its brief is grounded in that document. For live news
items, the "interview angle" is built from the headline only (plus the user's guides for
concepts) and clearly separates the announced headline fact from analysis — it never
invents deal figures, parties, or dates.
"""

from __future__ import annotations

from . import base
from .. import news, rag, sanitize

AGENT = "markets"

# The user's own uploaded deal (real figures come from their walkthrough document).
FEATURED_DEAL = {
    "id": "santander-webster",
    "date": "2026-02-03",
    "category": "ma",
    "headline": "Banco Santander to acquire Webster Financial for ~$12.2B",
    "source": "Your uploaded deal walkthrough",
    "parties": "Banco Santander (acquirer) / Webster Financial (target)",
    "value": "~$12.2B",
    "structure": "65% cash / 35% Santander shares (ADSs); closed 8/20/26",
    "featured": True,
}


def feed(category: str = "all") -> dict:
    # News feed removed (no reliable live connection). Markets focuses on grounded deal
    # prep from the user's own uploaded deal documents.
    return {"live": False, "source_mode": "documents", "featured_deal": FEATURED_DEAL, "items": []}


def deal_brief(item_id: str) -> dict:
    """Grounded brief for the featured deal, using the uploaded walkthrough."""
    if item_id != FEATURED_DEAL["id"]:
        return {"error": "Only the featured deal has a grounded brief. Use news_brief for headlines."}
    chunks = rag.retriever.retrieve("Santander Webster deal rationale multiple structure synergies", k=6, topic="deal")
    context = sanitize.format_context(chunks)
    system = (
        "You are the Markets & Deals agent. Write an interview-ready deal brief with four "
        "markdown sections using '### ' headers: '### What happened?', '### Why does it "
        "matter?', '### Why this transaction?', and '### What might an interviewer ask?' "
        "(3-4 bullet questions). Use ONLY the grounded excerpts with [n] citations. Do NOT "
        "invent figures, parties, or dates. End with '### Facts vs. interpretation' noting "
        "which claims are announced facts vs. your analysis, and '### Terminology' defining "
        "any jargon. Use markdown bullets ('- ') for lists."
    )
    res = base.run(AGENT, "deal_brief", system, f"{context}\n\nDeal: {FEATURED_DEAL['headline']}",
                   max_tokens=1600, detail={"item": item_id})
    return {"item": FEATURED_DEAL, "brief": res.text, "sources": [{"citation": c["citation"]} for c in chunks],
            "provenance": "retrieved", "usage": _usage(res), "error": res.error}


def news_brief(headline: str, source: str = "", url: str = "") -> dict:
    """Interview angle for a live headline. Works from the headline only; grounds concepts
    in the user's guides; never invents deal statistics."""
    chunks = rag.retriever.retrieve(headline, k=3)
    context = sanitize.format_context(chunks)
    system = (
        "You are the Markets & Deals agent. You are given ONLY a news HEADLINE (not the "
        "article). Produce a short interview angle in markdown with '### ' sections: "
        "'### What the headline says' (restate only what the headline states — do not add "
        "figures or details not in it), '### Why it matters for IB interviews' (your analysis, "
        "grounded in the excerpts with [n] where relevant), and '### Likely interviewer "
        "question' (one). Clearly mark analysis as interpretation. Never invent parties, "
        "values, dates, or quotes beyond the headline."
    )
    user = f"{context}\n\n{sanitize.wrap_untrusted('HEADLINE: ' + headline + ' (source: ' + source + ')', 'NEWS HEADLINE')}"
    res = base.run(AGENT, "news_brief", system, user, max_tokens=900, detail={"source": source})
    return {"headline": headline, "source": source, "url": url, "brief": res.text,
            "sources": [{"citation": c["citation"]} for c in chunks],
            "provenance": "ai_generated", "usage": _usage(res), "error": res.error}


def _usage(res) -> dict:
    return {"input_tokens": res.input_tokens, "cached_tokens": res.cached_tokens,
            "output_tokens": res.output_tokens, "cost_usd": res.cost_usd,
            "latency_s": res.latency_s, "model": res.model}
