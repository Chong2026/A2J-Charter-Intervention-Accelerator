"""Offline end-to-end test of run_monitor using canned pages (no network)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "monitor"))
sys.path.insert(0, str(Path(__file__).parent))

import run_monitor  # noqa: E402
import test_scc_parse as fx  # noqa: E402


def as_html(lines):
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


FEED = {"items": [
    {"id": "21602", "content_text": "Granted - New document published on 2026-08-06",
     "title": "His Majesty the King in right of Alberta v. Prabjot Singh Wirring - 2026-08-06",
     "url": "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/item/21602/index.do", "date_published": "2026-08-06"},
    {"id": "21559", "content_text": "Granted - New document published on 2026-07-02",
     "title": "H.D. v. His Majesty the King in Right of the Province of British Columbia - 2026-07-02",
     "url": "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/item/21559/index.do", "date_published": "2026-07-02"},
    {"id": "21659", "content_text": "Dismissed - New document published on 2026-09-17",
     "title": "Someone v. Someone - 2026-09-17",
     "url": "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/item/21659/index.do", "date_published": "2026-09-17"},
]}

PAGES = {
    "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/item/21602/index.do?iframe=true": as_html(fx.ITEM_ALBERTA),
    "https://decisions.scc-csc.ca/scc-csc/scc-l-csc-a/en/item/21559/index.do?iframe=true": as_html(fx.ITEM_BC),
    "https://www.scc-csc.ca/cases-dossiers/search-recherche/42224/": as_html(fx.DOCKET_ALBERTA),
    "https://www.scc-csc.ca/cases-dossiers/search-recherche/42219/": as_html(fx.DOCKET_BC),
}


class FakeResponse:
    def json(self):
        return FEED

    def raise_for_status(self):
        pass


class FakeFetcher:
    class session:  # noqa: N801
        @staticmethod
        def get(url, timeout=30):
            assert url == run_monitor.FEED_URL
            return FakeResponse()

    def get(self, url):
        return PAGES[url]


def test_end_to_end(tmp_path, capsys, monkeypatch):
    db = sqlite3.connect(tmp_path / "m.sqlite")
    db.executescript(run_monitor.SCHEMA)
    f = FakeFetcher()

    assert run_monitor.process_new_grants(db, f) == 2          # dismissed item ignored
    assert run_monitor.process_new_grants(db, f) == 0          # idempotent on second run
    run_monitor.refresh_recent(db, f)                          # nothing due for refresh today

    # No SMTP env vars set -> alert is skipped, not marked as sent
    for k in ["ALERT_SMTP_HOST", "ALERT_SMTP_PORT", "ALERT_SMTP_USER", "ALERT_SMTP_PASS", "ALERT_TO"]:
        monkeypatch.delenv(k, raising=False)
    run_monitor.maybe_send_alerts(db)
    unsent = db.execute("SELECT alerted FROM pending_cases WHERE is_charter=1").fetchall()
    assert all(a == 0 for (a,) in unsent)

    rows = dict(db.execute("SELECT case_no, is_charter FROM pending_cases"))
    assert rows == {"42224": 1, "42219": 0}
    due = db.execute("SELECT due_date FROM pending_deadlines WHERE case_no='42224' AND kind='intervention_motion'").fetchone()
    assert due == ("2026-12-01",)
    assert db.execute("SELECT COUNT(*) FROM pending_deadlines").fetchone()[0] == 15

    # Now configure SMTP and send: should call send_email once and mark cases alerted
    monkeypatch.setenv("ALERT_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("ALERT_SMTP_PORT", "465")
    monkeypatch.setenv("ALERT_SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("ALERT_SMTP_PASS", "pw")
    monkeypatch.setenv("ALERT_TO", "me@gmail.com")
    sent = {}
    def fake_send_email(**kwargs):
        sent.update(kwargs)
    monkeypatch.setattr(run_monitor, "send_email", fake_send_email)
    run_monitor.maybe_send_alerts(db)
    assert "42224" in sent["body"] and "2026-12-01" in sent["body"]
    assert "42219" not in sent["body"]  # 42219 is not Charter, must not appear
    alerted = dict(db.execute("SELECT case_no, alerted FROM pending_cases WHERE is_charter=1"))
    assert alerted == {"42224": 1}
    # Calling again should be a no-op (nothing left to alert)
    sent.clear()
    run_monitor.maybe_send_alerts(db)
    assert sent == {}

    run_monitor.report(db)
    out = capsys.readouterr().out
    assert "42224" in out and "2026-12-01  intervention_motion" in out and "42219" not in out.split("=== Charter")[1]
