"""Tests for the Monitor's health checks."""
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

import run_monitor  # noqa: E402
from run_monitor import Health, check_feed, check_stored_cases, format_health_email  # noqa: E402

TODAY = date(2026, 10, 12)


def item(i, text="Dismissed - New document published", d="2026-10-08"):
    return {"id": str(i), "url": f"u{i}", "title": f"t{i}", "content_text": text, "date_published": d}


def test_healthy_feed_has_no_problems():
    h = Health()
    check_feed([item(1), item(2, "Granted - New document published")], h, TODAY)
    assert h.problems == []


@pytest.mark.parametrize("items, expected", [
    ([], "returned no items"),
    ([{"id": "1"}], "missing expected fields"),
    ([item(1, "Accordée - nouveau document")], "wording may have changed"),
    ([item(1, d="2026-07-01")], "more than 60 days ago"),
    ([item(1, d="last week")], "Could not read feed dates"),
])
def test_feed_problems(items, expected):
    h = Health()
    check_feed(items, h, TODAY)
    assert any(expected in p for p in h.problems), h.problems


def make_db():
    db = sqlite3.connect(":memory:")
    run_monitor.ensure_schema(db)
    rows = [
        ("1", "2026-09-01", "Charter of Rights", ""),   # has schedule below -> fine
        ("2", "2026-09-01", "Contracts", ""),           # no schedule after 41 days -> warn
        ("3", "2026-10-05", "", ""),                    # too recent to judge -> fine
        ("4", "2026-09-10", "", ""),                    # no schedule and no keywords -> two warnings
        ("5", "2026-03-01", "", ""),                    # older than the 90-day window -> ignored
    ]
    db.executemany("INSERT INTO pending_cases (case_no, granted_on, keywords, summary) VALUES (?,?,?,?)", rows)
    db.execute("INSERT INTO pending_deadlines VALUES ('1', 'intervention_motion', '2026-12-01', '')")
    return db


def test_stored_case_checks():
    h = Health()
    check_stored_cases(make_db(), h, TODAY)
    joined = "\n".join(h.problems)
    assert "Case 2 " in joined and "Case 4 " in joined
    assert "Case 1 " not in joined and "Case 3 " not in joined and "Case 5 " not in joined
    assert sum("Case 4 " in p for p in h.problems) == 2


def test_health_email_format():
    subject, body = format_health_email(["A broke", "B broke"], "https://github.com/x/y/actions/runs/1")
    assert subject == "[Monitor health warning] 2 problem(s) found"
    assert "- A broke" in body and "Run log: https://github.com/x/y/actions/runs/1" in body


def test_send_health_warning_uses_health_to(monkeypatch):
    for k, v in {"ALERT_SMTP_HOST": "h", "ALERT_SMTP_PORT": "465", "ALERT_SMTP_USER": "u",
                 "ALERT_SMTP_PASS": "p", "ALERT_TO": "alerts@x", "HEALTH_TO": "me@x"}.items():
        monkeypatch.setenv(k, v)
    outbox = []
    monkeypatch.setattr(run_monitor, "send_email", lambda **kw: outbox.append(kw))
    run_monitor.send_health_warning(["feed broke"])
    assert outbox[0]["to_addr"] == "me@x" and "feed broke" in outbox[0]["body"]
    outbox.clear()
    run_monitor.send_health_warning([])          # nothing to report -> no email
    assert outbox == []


def test_send_health_warning_never_raises(monkeypatch):
    for k in ["ALERT_SMTP_HOST", "ALERT_SMTP_PORT", "ALERT_SMTP_USER", "ALERT_SMTP_PASS", "ALERT_TO"]:
        monkeypatch.setenv(k, "x" if k != "ALERT_SMTP_PORT" else "465")

    def boom(**kw):
        raise OSError("smtp down")
    monkeypatch.setattr(run_monitor, "send_email", boom)
    run_monitor.send_health_warning(["feed broke"])  # must not raise
