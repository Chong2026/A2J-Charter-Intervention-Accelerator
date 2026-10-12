"""Build the public Monitor website from data/monitor.sqlite.

Writes three files to site/ (published by GitHub Pages):
  index.html    open Charter cases, their Charter issues and intervention deadlines
  calendar.ics  intervention deadlines, subscribable in Outlook / Google / Apple Calendar
  cases.json    the same data as open JSON

Usage:  python build_site.py [--db data/monitor.sqlite] [--out site]
"""
import argparse
import html
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from alerts import KIND_LABELS
from charter_tags import LABELS

REPO_URL = "https://github.com/Chong2026/A2J-Charter-Intervention-Accelerator"
CLOSED_WINDOW_DAYS = 180
PENDING_WINDOW_DAYS = 60
CALENDAR_KINDS = ("intervention_motion", "intervener_factum")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def clean_title(title: str) -> str:
    return re.sub(r"\s*-\s*\d{4}-\d{2}-\d{2}\s*$", "", title or "").strip()


def load_cases(db) -> list[dict]:
    cols = {r[1] for r in db.execute("PRAGMA table_info(pending_cases)")}
    tags_col = "charter_tags" if "charter_tags" in cols else "''"
    rows = db.execute(
        f"SELECT case_no, title, docket_url, granted_on, appeal_from, lower_court_citation, {tags_col} "
        "FROM pending_cases WHERE is_charter = 1").fetchall()
    cases = []
    for case_no, title, url, granted, frm, lower, tags in rows:
        deadlines = [{"kind": k, "label": KIND_LABELS.get(k, k), "date": d} for k, d in db.execute(
            "SELECT kind, due_date FROM pending_deadlines WHERE case_no=? ORDER BY due_date", (case_no,))]
        motion = next((d["date"] for d in deadlines if d["kind"] == "intervention_motion"), None)
        cases.append({
            "case_no": case_no, "title": clean_title(title), "docket_url": url,
            "leave_granted": granted, "appeal_from": frm, "lower_court": lower,
            "charter_issues": [t for t in (tags or "").split(" | ") if t],
            "intervention_motion_deadline": motion, "deadlines": deadlines,
        })
    return cases


def split_cases(cases: list[dict], today: date):
    """-> (open, pending, closed). open: motion deadline today or later. pending: no schedule yet."""
    iso = today.isoformat()
    open_, pending, closed = [], [], []
    for c in cases:
        m = c["intervention_motion_deadline"]
        if m and m >= iso:
            open_.append(c)
        elif not m and c["leave_granted"] and c["leave_granted"] >= (today - timedelta(days=PENDING_WINDOW_DAYS)).isoformat():
            pending.append(c)
        elif m and m >= (today - timedelta(days=CLOSED_WINDOW_DAYS)).isoformat():
            closed.append(c)
    open_.sort(key=lambda c: c["intervention_motion_deadline"])
    pending.sort(key=lambda c: c["leave_granted"], reverse=True)
    closed.sort(key=lambda c: c["intervention_motion_deadline"], reverse=True)
    return open_, pending, closed


# ---------------------------------------------------------------------------
# Calendar (RFC 5545)
# ---------------------------------------------------------------------------
def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def build_ics(cases: list[dict], now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//A2J Charter Intervention Accelerator//Monitor//EN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:SCC Charter intervention deadlines",
             "X-WR-CALDESC:Deadlines to seek leave to intervene in SCC Charter appeals"]
    for c in cases:
        issues = ", ".join(c["charter_issues"]) or "Charter"
        for d in c["deadlines"]:
            if d["kind"] not in CALENDAR_KINDS:
                continue
            start = date.fromisoformat(d["date"])
            desc = (f"{c['title']} (SCC No. {c['case_no']}). Charter issues: {issues}. "
                    f"Verify on the SCC docket before relying on this date: {c['docket_url']}")
            lines += [
                "BEGIN:VEVENT",
                f"UID:scc-{c['case_no']}-{d['kind']}@a2j-charter-monitor",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(start + timedelta(days=1)).strftime('%Y%m%d')}",
                f"SUMMARY:{_ics_escape(d['label'] + ' – ' + c['title'])}",
                f"DESCRIPTION:{_ics_escape(desc)}",
                f"URL:{c['docket_url']}",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _esc(x) -> str:
    return html.escape(str(x or ""), quote=True)


def _nice_date(iso: str) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"  # no %-d: it is not supported on Windows


def _issue_chips(tags: list[str]) -> str:
    if not tags:
        return '<span class="chip chip-muted">Section not identified</span>'
    return "".join(
        f'<span class="chip" title="{_esc(LABELS.get(t, ""))}">{_esc(t)}</span>' for t in tags)


def _section_keys(tags: list[str]) -> str:
    """Space-separated base sections for the filter, e.g. 's7 s2' (doctrines map to their section)."""
    keys = set()
    for t in tags:
        m = re.match(r"s\. (\d+)", t)
        if m:
            keys.add(f"s{m.group(1)}")
    return " ".join(sorted(keys))


def _card(c: dict, today: date, state: str) -> str:
    m = c["intervention_motion_deadline"]
    if state == "open":
        days = (date.fromisoformat(m) - today).days
        urgency = "soon" if days <= 30 else ""
        when = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
        key = (f'<div class="deadline {urgency}"><span class="deadline-label">Motion for leave to intervene due</span>'
               f'<span class="deadline-date">{_esc(_nice_date(m))}</span><span class="deadline-left">{when}</span></div>')
    elif state == "pending":
        key = ('<div class="deadline"><span class="deadline-label">Intervention deadline</span>'
               '<span class="deadline-date">Not yet set</span>'
               '<span class="deadline-left">The Registrar usually sets the schedule within days of leave</span></div>')
    else:
        key = (f'<div class="deadline closed"><span class="deadline-label">Intervention motion deadline passed</span>'
               f'<span class="deadline-date">{_esc(_nice_date(m))}</span></div>')
    rows = "".join(f"<tr><td>{_esc(_nice_date(d['date']))}</td><td>{_esc(d['label'])}</td></tr>" for d in c["deadlines"])
    schedule = (f'<details><summary>Full schedule</summary><table><tbody>{rows}</tbody></table></details>'
                if rows else "")
    meta = [f"SCC No. {_esc(c['case_no'])}", f"From {_esc(c['appeal_from'])}" if c["appeal_from"] else "",
            f"Leave granted {_esc(_nice_date(c['leave_granted']))}" if c["leave_granted"] else "",
            _esc(c["lower_court"]) if c["lower_court"] else ""]
    return f"""
    <article class="case" data-sections="{_section_keys(c['charter_issues'])}">
      <h3><a href="{_esc(c['docket_url'])}">{_esc(c['title'])}</a></h3>
      <p class="meta">{' · '.join(x for x in meta if x)}</p>
      <div class="issues">{_issue_chips(c['charter_issues'])}</div>
      {key}
      {schedule}
    </article>"""


def build_html(cases: list[dict], today: date, now: datetime) -> str:
    open_, pending, closed = split_cases(cases, today)
    shown = open_ + pending
    sections = sorted({k for c in shown for k in _section_keys(c["charter_issues"]).split()},
                      key=lambda k: int(k[1:]))
    filters = "".join(f'<button type="button" data-filter="{k}">s. {k[1:]}</button>' for k in sections)
    open_html = "".join(_card(c, today, "open") for c in open_) or \
        '<p class="empty">No Charter appeal is currently open for intervention motions.</p>'
    pending_html = "".join(_card(c, today, "pending") for c in pending)
    closed_html = "".join(_card(c, today, "closed") for c in closed)
    updated = _nice_date(now.date().isoformat())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SCC Charter Intervention Monitor</title>
<meta name="description" content="Supreme Court of Canada Charter appeals open for intervention, with deadlines.">
<style>
:root {{
  --bg: #fbfaf7; --surface: #ffffff; --text: #1d1f24; --muted: #5d6270; --line: #e3e0d8;
  --accent: #1f5c7a; --accent-soft: #e6f0f4; --soon: #a3341f; --soon-soft: #fbece8; --chip: #f1eee6;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #15171b; --surface: #1d2026; --text: #e8e6e1; --muted: #a2a6b0; --line: #2f333b;
    --accent: #7fb8d4; --accent-soft: #1d3440; --soon: #f08a73; --soon-soft: #3a211b; --chip: #2a2e35;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
a {{ color: var(--accent); }}
.wrap {{ max-width: 860px; margin: 0 auto; padding: 0 16px; }}
header {{ border-bottom: 1px solid var(--line); padding: 40px 0 28px; }}
h1 {{ font-family: Georgia, "Times New Roman", serif; font-weight: 600; font-size: clamp(28px, 5vw, 38px);
  line-height: 1.15; margin: 0 0 10px; letter-spacing: -0.01em; }}
.lede {{ color: var(--muted); max-width: 640px; margin: 0 0 18px; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
.btn {{ display: inline-block; padding: 8px 14px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--surface); color: var(--text); text-decoration: none; font-size: 14px; }}
.btn.primary {{ background: var(--accent); border-color: var(--accent); color: var(--bg); }}
.updated {{ color: var(--muted); font-size: 13px; margin-top: 14px; }}
h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted);
  margin: 36px 0 12px; font-weight: 600; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 14px; }}
.filters button {{ font: inherit; font-size: 13px; padding: 4px 10px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line); background: var(--surface); color: var(--text); }}
.filters button[aria-pressed="true"] {{ background: var(--accent); border-color: var(--accent); color: var(--bg); }}
.case {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px;
  margin: 0 0 12px; }}
.case h3 {{ font-size: 18px; line-height: 1.35; margin: 0 0 4px; }}
.case h3 a {{ color: var(--text); text-decoration: none; }}
.case h3 a:hover {{ text-decoration: underline; }}
.meta {{ color: var(--muted); font-size: 14px; margin: 0 0 10px; }}
.issues {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }}
.chip {{ font-size: 13px; padding: 2px 9px; border-radius: 999px; background: var(--accent-soft); color: var(--text); }}
.chip-muted {{ background: var(--chip); color: var(--muted); }}
.deadline {{ display: grid; grid-template-columns: 1fr auto; gap: 2px 16px; padding: 10px 12px;
  border-radius: 8px; background: var(--chip); }}
.deadline.soon {{ background: var(--soon-soft); }}
.deadline-label {{ grid-column: 1 / -1; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted); }}
.deadline-date {{ font-size: 20px; font-weight: 600; }}
.deadline-left {{ align-self: center; font-size: 14px; color: var(--muted); }}
.deadline.soon .deadline-left {{ color: var(--soon); font-weight: 600; }}
.deadline.closed .deadline-date {{ font-size: 16px; color: var(--muted); }}
details {{ margin-top: 10px; font-size: 14px; }}
summary {{ cursor: pointer; color: var(--accent); }}
table {{ border-collapse: collapse; margin-top: 8px; width: 100%; }}
td {{ padding: 4px 0; border-bottom: 1px solid var(--line); vertical-align: top; }}
td:first-child {{ white-space: nowrap; padding-right: 16px; color: var(--muted); }}
.empty {{ color: var(--muted); }}
.closed-list .case {{ opacity: 0.8; }}
footer {{ border-top: 1px solid var(--line); margin-top: 40px; padding: 24px 0 48px; color: var(--muted); font-size: 14px; }}
footer p {{ margin: 0 0 10px; }}
@media (max-width: 520px) {{ .case {{ padding: 16px; }} .deadline {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>SCC Charter Intervention Monitor</h1>
    <p class="lede">Charter appeals the Supreme Court of Canada has agreed to hear, with the deadline to
      seek leave to intervene. Built for legal clinics and pro bono counsel deciding whether to bring
      a community's perspective to the Court.</p>
    <div class="actions">
      <a class="btn primary" href="calendar.ics">Add deadlines to your calendar</a>
      <a class="btn" href="cases.json">Data (JSON)</a>
      <a class="btn" href="{REPO_URL}">Source code</a>
    </div>
    <p class="updated">Updated {_esc(updated)} · checked weekly against the SCC's leave decisions</p>
  </div>
</header>
<main class="wrap">
  <h2>Open for intervention</h2>
  {f'<div class="filters" role="group" aria-label="Filter by Charter section"><button type="button" data-filter="" aria-pressed="true">All</button>{filters}</div>' if filters else ''}
  <div id="open-list">{open_html}{pending_html}</div>
  {f'<h2>Recently closed</h2><div class="closed-list">{closed_html}</div>' if closed_html else ''}
</main>
<footer>
  <div class="wrap">
    <p><strong>How this works.</strong> Each week the Monitor reads the SCC's public feed of leave decisions,
      keeps the applications that were granted, and flags Charter cases from the subject keywords the
      Registry assigns to each docket (96.7% accurate on a hand-checked sample of 60 dockets).
      Deadlines come from the Registrar's scheduling letter on the docket.</p>
    <p><strong>Always verify.</strong> This is a research tool, not legal advice. Confirm every date on the
      SCC docket and in the <a href="https://laws-lois.justice.gc.ca/eng/regulations/SOR-2002-156/">Rules of the Supreme Court of
      Canada</a> before relying on it. Some Charter cases may be missed or mislabelled.</p>
    <p>Part of the <a href="{REPO_URL}">A2J Charter Intervention Accelerator</a>, funded through the Innovation
      Fellowship of the Access to Algorithmic Justice (A2AJ) Project at Osgoode Hall Law School, York University,
      with support from the Law Foundation of Ontario. Code under the MIT Licence.</p>
  </div>
</footer>
<script>
(function () {{
  var buttons = document.querySelectorAll('.filters button');
  buttons.forEach(function (b) {{
    b.addEventListener('click', function () {{
      var key = b.getAttribute('data-filter');
      buttons.forEach(function (x) {{ x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); }});
      document.querySelectorAll('#open-list .case').forEach(function (card) {{
        var secs = (card.getAttribute('data-sections') || '').split(' ');
        card.hidden = key && secs.indexOf(key) === -1;
      }});
    }});
  }});
}})();
</script>
</body>
</html>
"""


def build_site(db_path: str, out_dir: str, today: date | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = today or now.date()
    db = sqlite3.connect(db_path)
    cases = load_cases(db)
    open_, pending, closed = split_cases(cases, today)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(build_html(cases, today, now), encoding="utf-8")
    (out / "calendar.ics").write_text(build_ics(open_ + pending, now), encoding="utf-8", newline="")
    (out / "cases.json").write_text(json.dumps({
        "generated": now.isoformat(timespec="seconds"), "source": REPO_URL,
        "open": open_, "schedule_pending": pending, "recently_closed": closed,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return {"open": len(open_), "pending": len(pending), "closed": len(closed)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/monitor.sqlite")
    ap.add_argument("--out", default="site")
    args = ap.parse_args()
    counts = build_site(args.db, args.out)
    print(f"Built {args.out}/: {counts['open']} open, {counts['pending']} awaiting schedule, "
          f"{counts['closed']} recently closed.")


if __name__ == "__main__":
    main()
