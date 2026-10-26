"""Agent D — Banker Relationship Manager.

Summarizes meeting notes and drafts personalized thank-you / follow-up emails. Meeting
notes are untrusted DATA; the agent never invents a detail the banker did not mention, and
never sends anything — it only drafts for the user to review, edit, copy, or save.
"""

from __future__ import annotations

import json

from . import base
from .. import sanitize

AGENT = "banker"


def summarize_meeting(notes: str, contact: dict | None = None) -> dict:
    who = ""
    if contact:
        who = f"Contact: {contact.get('name','')} — {contact.get('title','')}, {contact.get('firm','')} ({contact.get('group_name','')})\n"
    system = (
        "You are the Banker Relationship agent. Summarize the meeting using ONLY the notes. "
        "Do NOT invent anything not in the notes. Return STRICT JSON: {\"summary\":\"2-3 "
        "sentences\",\"key_insights\":[..],\"topics\":[..],\"personal_connections\":[..],"
        "\"next_steps\":[..],\"thank_you_detail\":\"one specific detail from the notes that can "
        "be referenced naturally in a thank-you email\"}. If a field has nothing in the notes, "
        "use an empty list or empty string. JSON only."
    )
    user = who + sanitize.wrap_untrusted(notes, "MEETING NOTES")
    res = base.run(AGENT, "summarize_meeting", system, user, max_tokens=1000)
    data = base.parse_json(res.text) or {}
    return {**{k: data.get(k) for k in
               ("summary", "key_insights", "topics", "personal_connections", "next_steps", "thank_you_detail")},
            "provenance": "ai_generated_from_notes",
            "usage": _usage(res), "error": res.error}


def draft_email(contact: dict, notes: str = "", tone_sample: str = "", purpose: str = "thank_you",
                meeting_summary: str = "") -> dict:
    name = contact.get("name", "there")
    first = name.split()[0] if name else "there"
    tone_block = sanitize.wrap_untrusted(tone_sample, "USER TONE/FORMAT SAMPLE") if tone_sample else \
        "(no sample provided — use a warm, concise, professional MBA-recruiting tone)"
    notes_block = sanitize.wrap_untrusted(notes, "MEETING NOTES") if notes else "(no notes provided)"
    system = (
        "You are the Banker Relationship agent. Draft a short, specific follow-up email. "
        "Match the user's tone/format sample if provided. Reference a REAL detail from the "
        "notes; never invent a detail the banker did not mention. Keep it to ~120-150 words. "
        "Return STRICT JSON: {\"to\":\"<email or ''>\",\"subject\":\"...\",\"body\":\"...\"}. "
        "The body must be ready to review and edit; do not include placeholders like [X] unless "
        "the information is genuinely missing. JSON only."
    )
    user = (f"Purpose: {purpose}\nRecipient: {name} ({contact.get('title','')}, {contact.get('firm','')})\n"
            f"Recipient first name: {first}\nRecipient email: {contact.get('email','')}\n\n"
            f"Tone sample:\n{tone_block}\n\nMeeting summary: {sanitize.clean(meeting_summary)}\n\n{notes_block}")
    res = base.run(AGENT, "draft_email", system, user, max_tokens=900)
    data = base.parse_json(res.text) or {}
    return {"to": data.get("to") or contact.get("email", ""),
            "subject": data.get("subject", f"Thank you — {first}"),
            "body": data.get("body", res.text),
            "provenance": "ai_generated", "usage": _usage(res), "error": res.error}


def prep_chat(person: str = "", firm: str = "", group: str = "", context: str = "") -> dict:
    """One-click prep for a coffee chat / networking meeting: tailored questions to ask,
    likely questions they'll ask, an opener, and a short pre-meeting brief. Grounded in the
    user's guides for any technical angle; never fabricates facts about the specific banker."""
    from .. import rag
    query = f"{firm} {group} FIG M&A banking interview talking points".strip()
    chunks = rag.retriever.retrieve(query, k=3, topic="fig" if "fig" in (group or "").lower() else None)
    context_block = sanitize.format_context(chunks)
    who = f"Person: {person or 'the banker'}\nFirm: {firm or '(unknown)'}\nGroup: {group or '(unknown)'}\n"
    system = (
        "You are the Banker Relationship agent preparing the student for a networking chat. "
        "Return STRICT JSON with: {\"opener\":\"one natural opening line\",\"questions_to_ask\":"
        "[5 thoughtful, specific questions tailored to the firm/group — mix of career-path, "
        "deal-experience, and culture; avoid generic ones],\"likely_questions\":[5 questions "
        "the banker may ask the student, e.g. why this firm/group, a technical one],\"prep_brief\":"
        "\"3-4 sentence brief on what to emphasize\",\"technical_note\":\"one concept to be ready "
        "to discuss, grounded in the excerpts with a citation if possible\"}. Do NOT invent facts "
        "about this specific person. JSON only."
    )
    user = f"{context_block}\n\n{who}\nExtra context from the student: {sanitize.clean(context)}"
    res = base.run(AGENT, "prep_chat", system, user, max_tokens=1400,
                   detail={"firm": firm, "group": group})
    data = base.parse_json(res.text) or {}
    return {
        "person": person, "firm": firm, "group": group,
        "opener": data.get("opener", ""),
        "questions_to_ask": data.get("questions_to_ask", []),
        "likely_questions": data.get("likely_questions", []),
        "prep_brief": data.get("prep_brief", ""),
        "technical_note": data.get("technical_note", ""),
        "sources": [{"citation": c["citation"]} for c in chunks],
        "provenance": "ai_generated", "usage": _usage(res), "error": res.error,
    }


def _usage(res) -> dict:
    return {"input_tokens": res.input_tokens, "cached_tokens": res.cached_tokens,
            "output_tokens": res.output_tokens, "cost_usd": res.cost_usd,
            "latency_s": res.latency_s, "model": res.model}
