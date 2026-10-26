"""SQLite persistence for IB Copilot.

Stores real application data: banker contacts, meetings/notes, email drafts, interview
practice sessions, imported calendar events, and the agent-run / token-usage log that
powers the Tokenomics view. All dashboard numbers come from here, not hardcoded values.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, firm TEXT, group_name TEXT, title TEXT, email TEXT,
  personal_connection TEXT, follow_up_status TEXT DEFAULT 'none',
  created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS meetings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id INTEGER, date TEXT, location TEXT, topics TEXT, notes TEXT,
  summary TEXT, next_steps TEXT, created_at REAL,
  FOREIGN KEY(contact_id) REFERENCES contacts(id)
);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contact_id INTEGER, meeting_id INTEGER, to_addr TEXT, subject TEXT, body TEXT,
  status TEXT DEFAULT 'draft', created_at REAL,
  FOREIGN KEY(contact_id) REFERENCES contacts(id)
);
CREATE TABLE IF NOT EXISTS practice (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mode TEXT, topic TEXT, question TEXT, answer TEXT,
  score INTEGER, rubric TEXT, feedback TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT DEFAULT 'manual', title TEXT, start TEXT, end TEXT, location TEXT,
  kind TEXT DEFAULT 'event', contact_id INTEGER, done INTEGER DEFAULT 0, created_at REAL
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent TEXT, action TEXT, status TEXT, steps INTEGER DEFAULT 1,
  model TEXT, model_calls INTEGER DEFAULT 0, tool_calls INTEGER DEFAULT 0,
  input_tokens INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
  cost_usd REAL, latency_s REAL, error TEXT, detail TEXT, created_at REAL
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ---------- contacts ----------
def add_contact(**k) -> int:
    now = time.time()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO contacts(name,firm,group_name,title,email,personal_connection,follow_up_status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (k.get("name"), k.get("firm"), k.get("group_name"), k.get("title"), k.get("email"),
             k.get("personal_connection"), k.get("follow_up_status", "pending"), now, now),
        )
        return cur.lastrowid


def list_contacts(q: str | None = None) -> list[dict]:
    with connect() as c:
        if q:
            like = f"%{q}%"
            return _rows(c.execute(
                "SELECT * FROM contacts WHERE name LIKE ? OR firm LIKE ? OR group_name LIKE ? ORDER BY updated_at DESC",
                (like, like, like)))
        return _rows(c.execute("SELECT * FROM contacts ORDER BY updated_at DESC"))


def get_contact(cid: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None


def set_followup(cid: int, status: str) -> None:
    with connect() as c:
        c.execute("UPDATE contacts SET follow_up_status=?, updated_at=? WHERE id=?", (status, time.time(), cid))


# ---------- meetings ----------
def add_meeting(**k) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO meetings(contact_id,date,location,topics,notes,summary,next_steps,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (k.get("contact_id"), k.get("date"), k.get("location"), k.get("topics"),
             k.get("notes"), k.get("summary"), k.get("next_steps"), time.time()))
        return cur.lastrowid


def meetings_for(cid: int) -> list[dict]:
    with connect() as c:
        return _rows(c.execute("SELECT * FROM meetings WHERE contact_id=? ORDER BY created_at DESC", (cid,)))


# ---------- drafts ----------
def add_draft(**k) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO drafts(contact_id,meeting_id,to_addr,subject,body,status,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (k.get("contact_id"), k.get("meeting_id"), k.get("to_addr"), k.get("subject"),
             k.get("body"), k.get("status", "draft"), time.time()))
        return cur.lastrowid


def list_drafts() -> list[dict]:
    with connect() as c:
        return _rows(c.execute("SELECT * FROM drafts ORDER BY created_at DESC"))


# ---------- practice ----------
def add_practice(**k) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO practice(mode,topic,question,answer,score,rubric,feedback,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (k.get("mode"), k.get("topic"), k.get("question"), k.get("answer"),
             k.get("score"), json.dumps(k.get("rubric")), k.get("feedback"), time.time()))
        return cur.lastrowid


def list_practice(limit: int = 50) -> list[dict]:
    with connect() as c:
        return _rows(c.execute("SELECT * FROM practice ORDER BY created_at DESC LIMIT ?", (limit,)))


def topic_averages() -> list[dict]:
    with connect() as c:
        return _rows(c.execute(
            "SELECT topic, COUNT(*) n, ROUND(AVG(score),1) avg_score FROM practice "
            "WHERE score IS NOT NULL GROUP BY topic ORDER BY avg_score ASC"))


# ---------- events ----------
def add_event(**k) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO events(source,title,start,end,location,kind,contact_id,done,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (k.get("source", "manual"), k.get("title"), k.get("start"), k.get("end"),
             k.get("location"), k.get("kind", "event"), k.get("contact_id"), k.get("done", 0), time.time()))
        return cur.lastrowid


def list_events(upcoming_only: bool = False) -> list[dict]:
    with connect() as c:
        rows = _rows(c.execute("SELECT * FROM events ORDER BY start ASC"))
    if upcoming_only:
        today = time.strftime("%Y-%m-%d")
        rows = [r for r in rows if (r.get("start") or "") >= today and not r.get("done")]
    return rows


# ---------- run / usage log ----------
def log_run(agent: str, action: str, result, steps: int = 1, tool_calls: int = 0,
            status: str = "ok", detail: dict | None = None) -> int:
    """Persist one agent run's measured usage. `result` is an llm.LLMResult-like object."""
    with connect() as c:
        cur = c.execute(
            "INSERT INTO runs(agent,action,status,steps,model,model_calls,tool_calls,"
            "input_tokens,cached_tokens,output_tokens,cost_usd,latency_s,error,detail,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (agent, action, "error" if getattr(result, "error", None) else status, steps,
             getattr(result, "model", None), getattr(result, "calls", 1), tool_calls,
             getattr(result, "input_tokens", None), getattr(result, "cached_tokens", None),
             getattr(result, "output_tokens", None), getattr(result, "cost_usd", None),
             getattr(result, "latency_s", None), getattr(result, "error", None),
             json.dumps(detail or {}), time.time()))
        return cur.lastrowid


def list_runs(limit: int = 50) -> list[dict]:
    with connect() as c:
        return _rows(c.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)))


def runs_today() -> int:
    cutoff = time.time() - 86400
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM runs WHERE created_at>=?", (cutoff,)).fetchone()[0]


# ---------- maintenance (safety: delete test data) ----------
def reset(scope: str = "all") -> dict:
    tables = {"contacts", "meetings", "drafts", "practice", "events", "runs"}
    targets = tables if scope == "all" else ({scope} & tables)
    with connect() as c:
        for t in targets:
            c.execute(f"DELETE FROM {t}")
    return {"reset": sorted(targets)}
