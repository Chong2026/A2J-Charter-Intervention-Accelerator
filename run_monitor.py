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

FEED_URL = "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/json/rss.do"
DOCKET_URL = "https://www.scc-csc.ca/cases-dossiers/search-recherche/{}/"
REFRESH_DAYS = 45
PAUSE_SECONDS = 1.0

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


def process_new_grants(db, fetcher: Fetcher) -> int:
    feed = fetcher.session.get(FEED_URL, timeout=30)
    feed.raise_for_status()
    items = feed.json()["items"]
    known = {r[0] for r in db.execute("SELECT feed_item_id FROM pending_cases")}
    new = [i for i in items if i["content_text"].startswith("Granted") and i["id"] not in known]
    print(f"Feed: {len(items)} items, {sum(i['content_text'].startswith('Granted') for i in items)} granted, "
          f"{len(new)} new to this database")

    for it in reversed(new):  # oldest first
        info = parse_item_lines(html_to_lines(fetcher.get(it["url"] + "?iframe=true")))
        if not info["case_no"]:
            print(f"  ! could not read case number for {it['url']}; skipped", file=sys.stderr)
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
        "SELECT case_no, title, docket_url, granted_on, appeal_from FROM pending_cases "
        "WHERE is_charter = 1 AND alerted = 0 ORDER BY granted_on"
    ).fetchall()
    cases = []
    for case_no, title, docket_url, granted_on, appeal_from in rows:
        deadlines = db.execute(
            "SELECT kind, due_date FROM pending_deadlines WHERE case_no=? ORDER BY due_date", (case_no,)
        ).fetchall()
        cases.append({"case_no": case_no, "title": title, "docket_url": docket_url,
                      "granted_on": granted_on, "appeal_from": appeal_from, "deadlines": deadlines})
    return cases


def mark_alerted(db, case_nos: list[str]):
    db.executemany("UPDATE pending_cases SET alerted = 1 WHERE case_no = ?", [(c,) for c in case_nos])
    db.commit()


def maybe_send_alerts(db):
    """Send one email covering all not-yet-alerted Charter cases, if SMTP is configured."""
    cases = get_unalerted_charter_cases(db)
    if not cases:
        print("\nNo new Charter-case alerts to send.")
        return

    required = ["ALERT_SMTP_HOST", "ALERT_SMTP_PORT", "ALERT_SMTP_USER", "ALERT_SMTP_PASS", "ALERT_TO"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"\n{len(cases)} Charter case(s) awaiting alert, but email is not configured "
              f"(missing: {', '.join(missing)}). Set these environment variables to enable email.")
        return

    subject, body = format_alert_email(cases)
    try:
        send_email(
            smtp_host=os.environ["ALERT_SMTP_HOST"],
            smtp_port=int(os.environ["ALERT_SMTP_PORT"]),
            smtp_user=os.environ["ALERT_SMTP_USER"],
            smtp_pass=os.environ["ALERT_SMTP_PASS"],
            from_addr=os.environ.get("ALERT_FROM", os.environ["ALERT_SMTP_USER"]),
            to_addr=os.environ["ALERT_TO"],
            subject=subject,
            body=body,
        )
    except Exception as e:
        print(f"\n! Failed to send alert email: {e}", file=sys.stderr)
        return

    mark_alerted(db, [c["case_no"] for c in cases])
    print(f"\nSent alert email for {len(cases)} Charter case(s) to {os.environ['ALERT_TO']}.")


def report(db):
    print("\n=== Charter cases with leave granted ===")
    cases = db.execute(
        "SELECT case_no, title, granted_on, appeal_from, charter_basis FROM pending_cases "
        "WHERE is_charter = 1 ORDER BY granted_on DESC").fetchall()
    if not cases:
        print("(none yet)")
    for case_no, title, granted_on, appeal_from, basis in cases:
        print(f"\n{case_no}  {title[:90]}\n  leave granted {granted_on}, from {appeal_from}, Charter flag via {basis}")
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
    db.executescript(SCHEMA)
    fetcher = Fetcher(contact)
    process_new_grants(db, fetcher)
    refresh_recent(db, fetcher)
    maybe_send_alerts(db)
    report(db)


if __name__ == "__main__":
    main()
