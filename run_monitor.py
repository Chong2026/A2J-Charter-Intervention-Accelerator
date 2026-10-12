"""Charter Intervention Monitor, v0: poll SCC leave feed, store new grants.

Usage (PowerShell):
    $env:SCC_MONITOR_CONTACT = "you@osgoode.yorku.ca"
    uv run --with requests --with beautifulsoup4 --with lxml python monitor/run_monitor.py

What it does:
  1. Reads the SCC 'Applications for Leave' JSON feed and keeps items marked Granted.
  2. For each grant not seen before: reads the decision page (case number, province,
     lower-court citation) and the SCC docket page (keywords, summary, and the
     Registrar's schedule with the intervention deadlines).
  3. Stores everything in SQLite and prints the Charter cases with their key dates.
Recently granted cases are re-checked on later runs until their schedule/keywords appear.
"""
import argparse
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

import requests

from scc_parse import (classify_charter, html_to_lines, parse_item_lines,
                       parse_keywords_summary, parse_schedule)
from alerts import format_alert_email, send_email
from charter_tags import matches_filter, parse_filter, tag_charter_case

FEED_URL = "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/json/rss.do"
DOCKET_URL = "https://www.scc-csc.ca/cases-dossiers/search-recherche/{}/"
REFRESH_DAYS = 45
PAUSE_SECONDS = 1.0
# Health-check thresholds
FEED_STALE_DAYS = 60       # newest leave decision in the feed older than this -> feed may be stuck
SCHEDULE_GRACE_DAYS = 21   # granted case with no Registrar schedule after this long -> parser may be broken
HEALTH_WINDOW_DAYS = 90    # only check cases granted within this many days

SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_cases (
    case_no TEXT PRIMARY KEY,
    feed_item_id TEXT UNIQUE,
    title TEXT, item_url TEXT, docket_url TEXT,
    granted_on TEXT, appeal_from TEXT, lower_court_citation TEXT,
    keywords TEXT, summary TEXT,
    is_charter INTEGER, charter_basis TEXT,
    first_seen TEXT, last_checked TEXT,
    alerted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending_deadlines (
    case_no TEXT NOT NULL, kind TEXT NOT NULL, due_date TEXT NOT NULL, raw_text TEXT,
    PRIMARY KEY (case_no, kind)
);
"""
TAG_SEP = " | "


def ensure_schema(db):
    """Create tables, and add columns introduced after the database was first created."""
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(pending_cases)")}
    if "charter_tags" not in cols:
        db.execute("ALTER TABLE pending_cases ADD COLUMN charter_tags TEXT")
    db.commit()


def retag_all(db):
    """(Re)compute Charter section tags for every Charter case from its stored keywords and summary.

    Cheap, so it runs every time: an edit to charter_tags.py applies to old cases too.
    """
    rows = db.execute("SELECT case_no, keywords, summary FROM pending_cases WHERE is_charter = 1").fetchall()
    db.executemany(
        "UPDATE pending_cases SET charter_tags = ? WHERE case_no = ?",
        [(TAG_SEP.join(tag_charter_case(kw or "", sm or "")), no) for no, kw, sm in rows])
    db.commit()


def split_tags(raw) -> list[str]:
    return [t for t in (raw or "").split(TAG_SEP) if t]


class Health:
    """Collects signs that the SCC pages or feed have changed so the Monitor is silently missing cases."""

    def __init__(self):
        self.problems: list[str] = []

    def warn(self, msg: str):
        self.problems.append(msg)
        print(f"! HEALTH: {msg}", file=sys.stderr)


def check_feed(items, health: Health, today: date):
    if not items:
        health.warn("The SCC leave feed returned no items.")
        return
    bad = [i for i in items if not all(k in i for k in ("id", "url", "title", "content_text", "date_published"))]
    if bad:
        health.warn(f"{len(bad)} feed item(s) are missing expected fields (id/url/title/content_text/date_published).")
    if not any(str(i.get("content_text", "")).startswith(("Granted", "Dismissed")) for i in items):
        health.warn("No feed item starts with 'Granted' or 'Dismissed'; the feed's wording may have changed.")
    dates = sorted(str(i.get("date_published", ""))[:10] for i in items if i.get("date_published"))
    if dates:
        try:
            newest = date.fromisoformat(dates[-1])
            if (today - newest).days > FEED_STALE_DAYS:
                health.warn(f"Newest item in the SCC leave feed is from {newest}, more than {FEED_STALE_DAYS} days ago.")
        except ValueError:
            health.warn(f"Could not read feed dates (e.g. {dates[-1]!r}).")


def check_stored_cases(db, health: Health, today: date):
    """Recently granted cases should have a Registrar schedule and docket keywords/summary."""
    window = (today - timedelta(days=HEALTH_WINDOW_DAYS)).isoformat()
    grace = (today - timedelta(days=SCHEDULE_GRACE_DAYS)).isoformat()
    rows = db.execute(
        "SELECT case_no, granted_on, keywords, summary FROM pending_cases "
        "WHERE granted_on >= ? AND granted_on <= ?", (window, grace)).fetchall()
    for case_no, granted_on, kw, summ in rows:
        has_schedule = db.execute("SELECT 1 FROM pending_deadlines WHERE case_no=? LIMIT 1", (case_no,)).fetchone()
        if not has_schedule:
            health.warn(f"Case {case_no} (leave granted {granted_on}) still has no deadlines parsed from the "
                        f"Registrar's letter: {DOCKET_URL.format(case_no)}")
        if not (kw or summ):
            health.warn(f"Case {case_no} (leave granted {granted_on}) has no keywords or summary on its docket "
                        f"page, so it cannot be classified: {DOCKET_URL.format(case_no)}")


def format_health_email(problems: list[str], run_url: str = "") -> tuple[str, str]:
    lines = ["The Charter Intervention Monitor ran but found signs that it may be missing cases.",
             "This usually means the SCC changed its website or feed. Please check:", ""]
    lines += [f"- {p}" for p in problems]
    if run_url:
        lines += ["", f"Run log: {run_url}"]
    return f"[Monitor health warning] {len(problems)} problem(s) found", "\n".join(lines)


class Fetcher:
    def __init__(self, contact: str):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"a2aj-charter-accelerator/0.1 (research; contact: {contact})"

    def get(self, url: str) -> str:
        time.sleep(PAUSE_SECONDS)  # be polite to the SCC servers
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        return r.content.decode("utf-8", errors="replace")  # avoids 'â' mojibake


def fetch_docket(fetcher: Fetcher, case_no: str) -> dict:
    lines = html_to_lines(fetcher.get(DOCKET_URL.format(case_no)))
    keywords, summary = parse_keywords_summary(lines)
    is_charter, basis = classify_charter(keywords, summary)
    return {"keywords": keywords, "summary": summary, "is_charter": is_charter,
            "charter_basis": basis, "deadlines": parse_schedule(lines)}


def save_docket(db, case_no: str, d: dict):
    db.execute(
        "UPDATE pending_cases SET keywords=?, summary=?, is_charter=?, charter_basis=?, last_checked=? "
        "WHERE case_no=?",
        (d["keywords"], d["summary"], d["is_charter"], d["charter_basis"],
         datetime.now().isoformat(timespec="seconds"), case_no))
    db.execute("DELETE FROM pending_deadlines WHERE case_no=?", (case_no,))
    db.executemany(
        "INSERT INTO pending_deadlines (case_no, kind, due_date, raw_text) VALUES (?,?,?,?)",
        [(case_no, x["kind"], x["due_date"], x["raw_text"]) for x in d["deadlines"]])


def process_new_grants(db, fetcher: Fetcher, health: Health | None = None) -> int:
    health = health or Health()
    feed = fetcher.session.get(FEED_URL, timeout=30)
    feed.raise_for_status()
    items = feed.json().get("items") or []
    check_feed(items, health, date.today())
    known = {r[0] for r in db.execute("SELECT feed_item_id FROM pending_cases")}
    new = [i for i in items if i["content_text"].startswith("Granted") and i["id"] not in known]
    print(f"Feed: {len(items)} items, {sum(i['content_text'].startswith('Granted') for i in items)} granted, "
          f"{len(new)} new to this database")

    for it in reversed(new):  # oldest first
        info = parse_item_lines(html_to_lines(fetcher.get(it["url"] + "?iframe=true")))
        if not info["case_no"]:
            health.warn(f"Could not read the case number for granted item {it['url']} (skipped).")
            continue
        db.execute(
            "INSERT OR IGNORE INTO pending_cases (case_no, feed_item_id, title, item_url, docket_url, "
            "granted_on, appeal_from, lower_court_citation, first_seen) VALUES (?,?,?,?,?,?,?,?,?)",
            (info["case_no"], it["id"], it["title"], it["url"], DOCKET_URL.format(info["case_no"]),
             info["decision_date"] or it["date_published"], info["appeal_from"],
             info["lower_court_citation"], date.today().isoformat()))
        save_docket(db, info["case_no"], fetch_docket(fetcher, info["case_no"]))
        db.commit()
        print(f"  + {info['case_no']}  {it['title'][:80]}")
    return len(new)


def refresh_recent(db, fetcher: Fetcher):
    cutoff = (date.today() - timedelta(days=REFRESH_DAYS)).isoformat()
    rows = db.execute(
        "SELECT case_no FROM pending_cases WHERE first_seen >= ? AND ("
        " NOT EXISTS (SELECT 1 FROM pending_deadlines d WHERE d.case_no = pending_cases.case_no)"
        " OR keywords IS NULL OR keywords = '') "
        "AND (last_checked IS NULL OR last_checked < ?)",
        (cutoff, datetime.now().replace(hour=0, minute=0, second=0).isoformat(timespec="seconds"))).fetchall()
    for (case_no,) in rows:
        save_docket(db, case_no, fetch_docket(fetcher, case_no))
        db.commit()
        print(f"  ~ refreshed {case_no}")


def get_unalerted_charter_cases(db) -> list[dict]:
    rows = db.execute(
        "SELECT case_no, title, docket_url, granted_on, appeal_from, charter_tags FROM pending_cases "
        "WHERE is_charter = 1 AND alerted = 0 ORDER BY granted_on"
    ).fetchall()
    cases = []
    for case_no, title, docket_url, granted_on, appeal_from, tags in rows:
        deadlines = db.execute(
            "SELECT kind, due_date FROM pending_deadlines WHERE case_no=? ORDER BY due_date", (case_no,)
        ).fetchall()
        cases.append({"case_no": case_no, "title": title, "docket_url": docket_url,
                      "granted_on": granted_on, "appeal_from": appeal_from, "deadlines": deadlines,
                      "tags": split_tags(tags)})
    return cases


def mark_alerted(db, case_nos: list[str]):
    db.executemany("UPDATE pending_cases SET alerted = 1 WHERE case_no = ?", [(c,) for c in case_nos])
    db.commit()


def plan_alert_emails(cases: list[dict], wanted: list[str], mode: str) -> tuple[list[tuple[str, str]], list[dict]]:
    """Decide which emails to send for the un-alerted Charter cases.

    Returns ([(subject, body), ...], cases_to_mark_alerted).
      * no ALERT_SECTIONS: one general email with every case.
      * ALERT_SECTIONS, mode "extra" (default): a priority email with the matching cases,
        plus the general email with every case.
      * ALERT_SECTIONS, mode "only": one email with the matching cases; the rest are not
        sent and stay un-alerted (they will be sent if the filter is later widened).
    """
    if not wanted:
        return ([format_alert_email(cases)] if cases else []), cases
    matching = [c for c in cases if matches_filter(c["tags"], wanted)]
    if mode == "only":
        return ([format_alert_email(matching)] if matching else []), matching
    emails = []
    if matching:
        emails.append(format_alert_email(matching, focus=wanted))
    if cases:
        emails.append(format_alert_email(cases))
    return emails, cases


SMTP_REQUIRED = ["ALERT_SMTP_HOST", "ALERT_SMTP_PORT", "ALERT_SMTP_USER", "ALERT_SMTP_PASS", "ALERT_TO"]


def smtp_send(subject: str, body: str, to_addr: str | None = None):
    """Send one email with the ALERT_SMTP_* settings. Raises on failure."""
    send_email(
        smtp_host=os.environ["ALERT_SMTP_HOST"],
        smtp_port=int(os.environ["ALERT_SMTP_PORT"]),
        smtp_user=os.environ["ALERT_SMTP_USER"],
        smtp_pass=os.environ["ALERT_SMTP_PASS"],
        from_addr=os.environ.get("ALERT_FROM") or os.environ["ALERT_SMTP_USER"],
        to_addr=to_addr or os.environ["ALERT_TO"],
        subject=subject,
        body=body,
    )


def send_health_warning(problems: list[str]):
    """Email the maintainer (HEALTH_TO, else ALERT_TO). Never raises."""
    if not problems:
        return
    if any(not os.environ.get(k) for k in SMTP_REQUIRED):
        print("! Health problems found but email is not configured; see the messages above.", file=sys.stderr)
        return
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                   f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    subject, body = format_health_email(problems, run_url)
    try:
        smtp_send(subject, body, os.environ.get("HEALTH_TO") or None)
        print(f"Sent: {subject}")
    except Exception as e:
        print(f"! Could not send the health warning email: {e}", file=sys.stderr)


def maybe_send_alerts(db):
    """Email the not-yet-alerted Charter cases, if SMTP is configured.

    ALERT_SECTIONS (e.g. "s. 7, s. 15") picks sections of special interest, and
    ALERT_SECTIONS_MODE says what to do with them: "extra" (default) sends an additional
    priority email for matching cases on top of the general alert; "only" sends just the
    matching cases. See plan_alert_emails.
    """
    wanted = parse_filter(os.environ.get("ALERT_SECTIONS"))
    mode = (os.environ.get("ALERT_SECTIONS_MODE") or "extra").strip().lower()
    if mode not in ("extra", "only"):
        print(f"\n! Unknown ALERT_SECTIONS_MODE '{mode}', using 'extra'.", file=sys.stderr)
        mode = "extra"
    cases = get_unalerted_charter_cases(db)
    emails, to_mark = plan_alert_emails(cases, wanted, mode)
    if wanted:
        n = sum(matches_filter(c["tags"], wanted) for c in cases)
        print(f"\nSections of interest: {', '.join(wanted)} (mode: {mode}); "
              f"{n} of {len(cases)} un-alerted Charter case(s) match")
    if not emails:
        print("\nNo new Charter-case alerts to send.")
        return

    missing = [k for k in SMTP_REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"\n{len(to_mark)} Charter case(s) awaiting alert, but email is not configured "
              f"(missing: {', '.join(missing)}). Set these environment variables to enable email.")
        return

    for subject, body in emails:
        try:
            smtp_send(subject, body)
        except Exception as e:
            print(f"\n! Failed to send alert email: {e}", file=sys.stderr)
            return  # nothing marked, so the next run tries again
        print(f"\nSent: {subject}")

    mark_alerted(db, [c["case_no"] for c in to_mark])
    print(f"Marked {len(to_mark)} Charter case(s) as alerted ({os.environ['ALERT_TO']}).")


def report(db):
    print("\n=== Charter cases with leave granted ===")
    cases = db.execute(
        "SELECT case_no, title, granted_on, appeal_from, charter_basis, charter_tags FROM pending_cases "
        "WHERE is_charter = 1 ORDER BY granted_on DESC").fetchall()
    if not cases:
        print("(none yet)")
    for case_no, title, granted_on, appeal_from, basis, tags in cases:
        print(f"\n{case_no}  {title[:90]}\n  leave granted {granted_on}, from {appeal_from}, Charter flag via {basis}")
        print(f"  Charter issues: {', '.join(split_tags(tags)) or 'section not identified'}")
        for kind, due in db.execute(
                "SELECT kind, due_date FROM pending_deadlines WHERE case_no=? ORDER BY due_date", (case_no,)):
            print(f"    {due}  {kind}")
    total = db.execute("SELECT COUNT(*) FROM pending_cases").fetchone()[0]
    print(f"\n{total} granted case(s) stored in total; {len(cases)} flagged as Charter.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/monitor.sqlite", help="SQLite file (default: data/monitor.sqlite)")
    args = ap.parse_args()

    contact = os.environ.get("SCC_MONITOR_CONTACT")
    if not contact:
        sys.exit('Set your contact email first, e.g. PowerShell:  $env:SCC_MONITOR_CONTACT = "you@osgoode.yorku.ca"')

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    db = sqlite3.connect(args.db)
    ensure_schema(db)
    fetcher = Fetcher(contact)
    health = Health()
    try:
        process_new_grants(db, fetcher, health)
        refresh_recent(db, fetcher)
        retag_all(db)
        check_stored_cases(db, health, date.today())
        maybe_send_alerts(db)
        report(db)
    except Exception as e:
        health.warn(f"The Monitor crashed: {type(e).__name__}: {e}")
        send_health_warning(health.problems)
        raise
    if health.problems:
        send_health_warning(health.problems)
        sys.exit(2)  # marks the GitHub Actions run as failed, so GitHub also notifies you


if __name__ == "__main__":
    main()
