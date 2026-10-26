"""Safe local Outlook calendar import.

Reads an Outlook-exported calendar (.ics file OR a month-grid print-to-PDF) with no OAuth
and no mailbox access, and stores events in the local DB. Recruiting-relevant events
(coffee chats, firm events, interviews, info sessions) are tagged so the dashboard can
surface them. Nothing is ever sent or modified in Outlook.
"""

from __future__ import annotations

import io
import re

from icalendar import Calendar
from pypdf import PdfReader

from . import db

_RECRUIT_HINTS = ("coffee", "chat", "network", "interview", "info session", "recruit",
                  "banker", "superday", "case", "call with", "hiresom", "wall street prep",
                  "open hou", "yale som", "nikita krishnan /", "jpm", "morgan stanley",
                  "goldman", "citi", "bcg", "evercore", "lazard", "ubs", "barclays",
                  "rbc", "jefferies", "centerview", "moelis", "pjt", "wells fargo")
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def _kind(title: str) -> str:
    t = (title or "").lower()
    return "recruiting" if any(h in t for h in _RECRUIT_HINTS) else "event"


def _fmt(dt) -> str:
    try:
        return dt.dt.strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return str(getattr(dt, "dt", ""))


def import_ics(raw: bytes, recruiting_only: bool = True) -> dict:
    cal = Calendar.from_ical(raw)
    added = skipped = 0
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        title = str(comp.get("summary", "(untitled)"))
        if recruiting_only and _kind(title) != "recruiting":
            skipped += 1
            continue
        start = _fmt(comp.get("dtstart")) if comp.get("dtstart") else ""
        end = _fmt(comp.get("dtend")) if comp.get("dtend") else ""
        loc = str(comp.get("location", "")) if comp.get("location") else ""
        db.add_event(source="outlook_ics", title=title, start=start, end=end,
                     location=loc, kind="recruiting")
        added += 1
    return {"imported": added, "skipped_non_recruiting": skipped}


def parse_month_pdf(raw: bytes) -> list[dict]:
    """Parse an Outlook month-grid print-to-PDF into events with dates.

    Maps each 'HH:MM Title' fragment to its day cell via x (weekday column) and y (week
    row), then to the dated cell header (e.g. '27 Sep', '1 Oct'). Returns a list of
    {title, start} dicts. Titles are often truncated by Outlook's cell width."""
    reader = PdfReader(io.BytesIO(raw))
    frags: list[tuple[float, float, str]] = []

    def visit(t, cm, tm, fd, fs):
        if t.strip():
            frags.append((round(float(tm[4]), 1), round(float(tm[5]), 1), t.strip()))

    for page in reader.pages:
        page.extract_text(visitor_text=visit)

    # Base month/year from the "Month YYYY" title.
    base_year, base_month = 2026, 1
    for _, _, txt in frags:
        m = re.match(r"^([A-Z][a-z]+)\s+(\d{4})$", txt)
        if m and m.group(1)[:3].title() in _MONTHS:
            base_month = _MONTHS[m.group(1)[:3].title()]
            base_year = int(m.group(2))
            break

    from collections import defaultdict

    date_re = re.compile(r"^(\d{1,2})(?:\s+([A-Z][a-z]{2}))?$")
    time_re = re.compile(r"^(\d{1,2}):(\d{2})\s*(.*)$")
    weekdays = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"}

    # Date-cell headers define the grid columns and week rows.
    headers = [(x, y, int(m.group(1)), m.group(2))
               for x, y, txt in frags if (m := date_re.match(txt))]
    if not headers:
        return []
    week_rows = sorted({h[1] for h in headers})
    week_set = {round(w) for w in week_rows}
    col_centers = sorted({round(h[0]) for h in headers})

    def col_idx(x):
        return min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - x))

    def week_idx(y):
        idx = 0
        for i, wy in enumerate(week_rows):
            if y >= wy - 1:
                idx = i
        return idx

    # Seed the running month from the first labeled cell (the grid may start on the
    # previous month's trailing days, e.g. "27 Sep" when viewing October).
    first_abbr = None
    for wi in range(len(week_rows)):
        for ci in range(len(col_centers)):
            for hx, hy, day, abbr in headers:
                if hy == week_rows[wi] and col_idx(hx) == ci and abbr and abbr.title() in _MONTHS:
                    first_abbr = _MONTHS[abbr.title()]
                    break
            if first_abbr:
                break
        if first_abbr:
            break
    if first_abbr is None:
        cur_m, cur_y = base_month, base_year
    else:
        cur_m = first_abbr
        cur_y = base_year if first_abbr <= base_month else base_year - 1

    # Dated cell map, in reading order so bare day-numbers inherit the current month.
    cell_date = {}
    for wi in range(len(week_rows)):
        for ci in range(len(col_centers)):
            for hx, hy, day, abbr in headers:
                if hy == week_rows[wi] and col_idx(hx) == ci:
                    if abbr and abbr.title() in _MONTHS:
                        nm = _MONTHS[abbr.title()]
                        if nm < cur_m:          # only a Dec -> Jan wrap decreases the month
                            cur_y += 1
                        cur_m = nm
                    cell_date[(ci, wi)] = (cur_y, cur_m, day)
                    break

    # Group remaining fragments into event lines by (column, y-row); time and title are
    # separate fragments on the same row.
    groups: dict[tuple[int, int], list[tuple[float, str]]] = defaultdict(list)
    for x, y, txt in frags:
        if txt in weekdays or txt == "Calendar" or re.match(r"^[A-Z][a-z]+\s+\d{4}$", txt):
            continue
        if date_re.match(txt) and round(y) in week_set:
            continue
        if not txt.strip() or txt[0] == "":
            continue
        groups[(col_idx(x), round(y))].append((x, txt))

    out = []
    for (ci, yrow), items in groups.items():
        items.sort()
        line = " ".join(t.strip() for _, t in items).strip()
        tm_ = time_re.match(line)
        if not tm_:
            continue
        key = (ci, week_idx(yrow))
        if key not in cell_date:
            continue
        yr, mo, dy = cell_date[key]
        hh, mm = int(tm_.group(1)), int(tm_.group(2))
        title = (tm_.group(3) or "").strip() or "(untitled)"
        out.append({"title": title, "start": f"{yr:04d}-{mo:02d}-{dy:02d} {hh:02d}:{mm:02d}"})
    out.sort(key=lambda e: e["start"])
    return out


def import_pdf(raw: bytes, recruiting_only: bool = True) -> dict:
    events = parse_month_pdf(raw)
    added = skipped = 0
    for e in events:
        if recruiting_only and _kind(e["title"]) != "recruiting":
            skipped += 1
            continue
        db.add_event(source="outlook_pdf", title=e["title"], start=e["start"],
                     end="", location="", kind="recruiting")
        added += 1
    return {"imported": added, "skipped_non_recruiting": skipped}
