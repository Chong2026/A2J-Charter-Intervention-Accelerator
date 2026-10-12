"""Tests for the public site builder."""
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import build_site  # noqa: E402
import run_monitor  # noqa: E402

TODAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)


def make_db(path):
    db = sqlite3.connect(path)
    run_monitor.ensure_schema(db)
    rows = [  # case_no, title, granted_on, is_charter, tags, keywords
        ("42224", "His Majesty the King in right of Alberta v. Prabjot Singh Wirring - 2026-08-06", "2026-08-06", 1,
         "s. 1 | s. 2(a) | s. 15"),
        ("40001", "Old v. Closed - 2026-03-01", "2026-03-01", 1, "s. 8"),
        ("40002", "New v. Pending - 2026-10-08", "2026-10-08", 1, ""),
        ("40003", "Contract v. Dispute - 2026-09-01", "2026-09-01", 0, ""),
        ("40004", "Ancient v. Case - 2024-01-01", "2024-01-01", 1, "s. 7"),
    ]
    for no, title, granted, charter, tags in rows:
        db.execute("INSERT INTO pending_cases (case_no, title, docket_url, granted_on, appeal_from, is_charter, "
                   "charter_tags) VALUES (?,?,?,?,?,?,?)",
                   (no, title, f"https://www.scc-csc.ca/cases-dossiers/search-recherche/{no}/", granted,
                    "Alberta", charter, tags))
    deadlines = [("42224", "intervention_motion", "2026-12-01"), ("42224", "intervener_factum", "2027-02-15"),
                 ("40001", "intervention_motion", "2026-07-01"), ("40003", "intervention_motion", "2026-12-01"),
                 ("40004", "intervention_motion", "2024-05-01")]
    db.executemany("INSERT INTO pending_deadlines (case_no, kind, due_date) VALUES (?,?,?)", deadlines)
    db.commit()


def test_build_site(tmp_path):
    make_db(tmp_path / "m.sqlite")
    counts = build_site.build_site(str(tmp_path / "m.sqlite"), str(tmp_path / "site"), TODAY, NOW)
    assert counts == {"open": 1, "pending": 1, "closed": 1}   # 40003 not Charter; 40004 too old

    page = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "His Majesty the King in right of Alberta v. Prabjot Singh Wirring</a>" in page   # date suffix removed
    assert "December 1, 2026" in page and "in 50 days" in page
    assert 'data-sections="s1 s15 s2"' in page and 'data-filter="s15"' in page
    assert "Not yet set" in page and "Recently closed" in page
    assert "Contract v. Dispute" not in page and "Ancient v. Case" not in page
    assert "Law Foundation of Ontario" in page

    data = json.loads((tmp_path / "site" / "cases.json").read_text(encoding="utf-8"))
    assert [c["case_no"] for c in data["open"]] == ["42224"]
    assert data["open"][0]["charter_issues"] == ["s. 1", "s. 2(a)", "s. 15"]

    ics = (tmp_path / "site" / "calendar.ics").read_bytes().decode("utf-8")
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 2                                       # motion + intervener factum
    assert "DTSTART;VALUE=DATE:20261201" in ics and "DTEND;VALUE=DATE:20261202" in ics
    assert all(len(line.encode("utf-8")) <= 75 for line in ics.split("\r\n"))   # RFC 5545 line length


def test_html_is_escaped(tmp_path):
    db = sqlite3.connect(tmp_path / "m.sqlite")
    run_monitor.ensure_schema(db)
    db.execute("INSERT INTO pending_cases (case_no, title, granted_on, is_charter, charter_tags) "
               "VALUES ('1', '<script>alert(1)</script> v. R', '2026-10-01', 1, '')")
    db.commit()
    build_site.build_site(str(tmp_path / "m.sqlite"), str(tmp_path / "site"), TODAY, NOW)
    page = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_empty_database(tmp_path):
    sqlite3.connect(tmp_path / "m.sqlite").close()
    db = sqlite3.connect(tmp_path / "m.sqlite"); run_monitor.ensure_schema(db); db.close()
    counts = build_site.build_site(str(tmp_path / "m.sqlite"), str(tmp_path / "site"), TODAY, NOW)
    assert counts == {"open": 0, "pending": 0, "closed": 0}
    assert "No Charter appeal is currently open" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
