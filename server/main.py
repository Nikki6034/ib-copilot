"""IB Copilot — FastAPI application.

Serves the single-page UI and the JSON API. All model calls and secrets stay here on the
server; the browser only talks to these endpoints. Agent calls go through the orchestrator.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, orchestrator, rag, readiness, usage
from .agents import markets
from . import ics_import, safety_test

app = FastAPI(title="IB Copilot")


@app.on_event("startup")
def _startup():
    db.init_db()
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # Build the retrieval index on first run so a fresh clone works with no extra steps.
    if not rag.retriever.ready:
        try:
            rag.build_index()
        except Exception as e:  # noqa: BLE001
            print(f"[startup] index build skipped: {e}")
    if rag.retriever.ready:
        rag.retriever.load()


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": f"{type(exc).__name__}: {str(exc)[:200]}"})


# ---------------- API ----------------
@app.get("/api/config")
def api_config():
    s = config.status()
    s["index_ready"] = rag.retriever.ready
    return s


class AgentReq(BaseModel):
    action: str
    params: dict = {}


@app.post("/api/agent")
def api_agent(req: AgentReq):
    try:
        return {"ok": True, "result": orchestrator.dispatch(req.action, req.params)}
    except orchestrator.OrchestratorError as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


@app.get("/api/documents")
def api_documents():
    if not rag.retriever.ready:
        return {"ready": False, "documents": []}
    return {"ready": True, "documents": rag.retriever.documents()}


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    name = file.filename or "upload"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in config.ALLOWED_UPLOAD_EXT:
        return JSONResponse(status_code=400, content={"error": f"Unsupported type {ext}. Allowed: {sorted(config.ALLOWED_UPLOAD_EXT)}"})
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        return JSONResponse(status_code=400, content={"error": f"File exceeds {config.MAX_UPLOAD_MB} MB limit"})
    dest = config.UPLOADS_DIR / name
    dest.write_bytes(data)
    stats = rag.build_index()
    rag.retriever.load()
    return {"ok": True, "file": name, "indexed_chunks": stats["chunks"]}


# ---- dashboard (all real data from the DB) ----
@app.get("/api/dashboard")
def api_dashboard():
    practice = db.list_practice(limit=5)
    weak = db.topic_averages()[:4]
    contacts = db.list_contacts()
    followups = [c for c in contacts if (c.get("follow_up_status") or "") in ("pending", "due")]
    events = db.list_events(upcoming_only=True)[:6]
    feed = markets.feed("all")
    deals = []
    if feed.get("featured_deal"):
        deals.append({"headline": feed["featured_deal"]["headline"], "date": feed["featured_deal"]["date"],
                      "parties": feed["featured_deal"].get("parties", ""), "featured": True})
    for it in feed.get("items", [])[:4]:
        deals.append({"headline": it["headline"], "date": it.get("date", ""), "parties": it.get("source", ""), "featured": False})
    trend = [{"score": p["score"], "topic": p["topic"], "at": p["created_at"]}
             for p in reversed(db.list_practice(limit=12)) if p.get("score") is not None]
    return {
        "readiness": readiness.compute(),
        "today_plan": _today_plan(weak, events),
        "upcoming_events": events,
        "recent_practice": practice,
        "weak_topics": weak,
        "performance_trend": trend,
        "deals_to_review": deals[:5],
        "news_live": feed["live"],
        "banker_followups": followups[:6],
        "counts": {"contacts": len(contacts), "practice_sessions": len(db.list_practice(10000)),
                   "drafts": len(db.list_drafts()), "events": len(db.list_events())},
    }


def _today_plan(weak, events):
    plan = []
    if weak:
        plan.append(f"Revise your weakest topic: {weak[0]['topic']} (avg {weak[0]['avg_score']}).")
    else:
        plan.append("Run your first mock interview to start tracking weak topics.")
    if events:
        plan.append(f"Prep for upcoming: {events[0]['title']} ({events[0]['start']}).")
    plan.append("Review the featured FIG deal (Santander/Webster) and draft one follow-up.")
    return plan


# ---- contacts / meetings / drafts ----
class ContactReq(BaseModel):
    name: str
    firm: str = ""
    group_name: str = ""
    title: str = ""
    email: str = ""
    personal_connection: str = ""
    follow_up_status: str = "pending"


@app.get("/api/contacts")
def api_contacts(q: str = ""):
    return {"contacts": db.list_contacts(q or None)}


@app.post("/api/contacts")
def api_add_contact(c: ContactReq):
    cid = db.add_contact(**c.model_dump())
    return {"ok": True, "id": cid}


@app.get("/api/contacts/{cid}")
def api_contact(cid: int):
    c = db.get_contact(cid)
    if not c:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"contact": c, "meetings": db.meetings_for(cid)}


class FollowupReq(BaseModel):
    status: str


@app.post("/api/contacts/{cid}/followup")
def api_followup(cid: int, r: FollowupReq):
    db.set_followup(cid, r.status)
    return {"ok": True}


class MeetingReq(BaseModel):
    contact_id: int
    date: str = ""
    location: str = ""
    topics: str = ""
    notes: str = ""
    summary: str = ""
    next_steps: str = ""


@app.post("/api/meetings")
def api_add_meeting(m: MeetingReq):
    mid = db.add_meeting(**m.model_dump())
    return {"ok": True, "id": mid}


class DraftReq(BaseModel):
    contact_id: int | None = None
    meeting_id: int | None = None
    to_addr: str = ""
    subject: str = ""
    body: str = ""


@app.get("/api/drafts")
def api_drafts():
    return {"drafts": db.list_drafts()}


@app.post("/api/drafts")
def api_add_draft(d: DraftReq):
    did = db.add_draft(**d.model_dump())
    return {"ok": True, "id": did}


@app.get("/api/drafts/{did}/eml")
def api_draft_eml(did: int):
    drafts = {x["id"]: x for x in db.list_drafts()}
    d = drafts.get(did)
    if not d:
        return JSONResponse(status_code=404, content={"error": "not found"})
    eml = (f"To: {d.get('to_addr','')}\r\nSubject: {d.get('subject','')}\r\n"
           f"X-Unsent: 1\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{d.get('body','')}\r\n")
    return PlainTextResponse(eml, headers={
        "Content-Disposition": f'attachment; filename="draft_{did}.eml"'})


# ---- practice / trends ----
@app.get("/api/practice")
def api_practice():
    return {"sessions": db.list_practice(50), "topic_averages": db.topic_averages()}


# ---- calendar / events ----
@app.get("/api/events")
def api_events():
    return {"events": db.list_events()}


class EventReq(BaseModel):
    title: str
    start: str = ""
    end: str = ""
    location: str = ""
    kind: str = "event"


@app.post("/api/events")
def api_add_event(e: EventReq):
    return {"ok": True, "id": db.add_event(source="manual", **e.model_dump())}


@app.post("/api/calendar/import")
async def api_calendar_import(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not (name.endswith(".ics") or name.endswith(".pdf")):
        return JSONResponse(status_code=400, content={"error": "Please upload an Outlook .ics export or a month-view print-to-PDF"})
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        return JSONResponse(status_code=400, content={"error": "File too large"})
    try:
        if name.endswith(".pdf"):
            return {"ok": True, "format": "pdf", **ics_import.import_pdf(data)}
        return {"ok": True, "format": "ics", **ics_import.import_ics(data)}
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"error": f"Could not parse calendar: {str(e)[:150]}"})


# ---- tokenomics / runs / architecture ----
@app.get("/api/usage")
def api_usage():
    return usage.summary()


@app.get("/api/runs")
def api_runs():
    return {"runs": db.list_runs(50)}


@app.get("/api/architecture")
def api_architecture():
    return {"agents": orchestrator.AGENTS, "actions": sorted(orchestrator.ACTIONS.keys())}


# ---- safety ----
@app.post("/api/safety/test")
def api_safety():
    return safety_test.run_safety_test()


# ---- reset test data ----
class ResetReq(BaseModel):
    scope: str = "all"


@app.post("/api/reset")
def api_reset(r: ResetReq):
    return {"ok": True, **db.reset(r.scope)}


# ---------------- static frontend ----------------
app.mount("/assets", StaticFiles(directory=str(config.WEB_DIR / "assets")), name="assets")


_NOCACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/styles.css")
def _css():
    return FileResponse(str(config.WEB_DIR / "styles.css"), media_type="text/css", headers=_NOCACHE)


@app.get("/app.js")
def _js():
    return FileResponse(str(config.WEB_DIR / "app.js"), media_type="application/javascript", headers=_NOCACHE)


@app.get("/")
def _index():
    return FileResponse(str(config.WEB_DIR / "index.html"), headers=_NOCACHE)
