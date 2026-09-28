"""Tests for alerts.py: pure formatting + mocked SMTP send."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "monitor"))

from alerts import format_alert_email, send_email  # noqa: E402

CASE = {
    "case_no": "42224",
    "title": "His Majesty the King in right of Alberta v. Prabjot Singh Wirring",
    "docket_url": "https://www.scc-csc.ca/cases-dossiers/search-recherche/42224/",
    "granted_on": "2026-08-06",
    "appeal_from": "Alberta",
    "deadlines": [("intervention_motion", "2026-12-01"), ("appellant_factum", "2026-11-03")],
}

CASE_NO_DEADLINES = {**CASE, "case_no": "41818", "deadlines": []}


def test_no_cases_gives_empty_email():
    assert format_alert_email([]) == ("", "")


def test_single_case_subject_and_body():
    subject, body = format_alert_email([CASE])
    assert subject == "1 new Charter case granted leave to appeal at the SCC"
    assert "Wirring" in body
    assert "Case No. 42224" in body
    assert "leave granted 2026-08-06" in body
    assert "Motion for leave to intervene due: 2026-12-01" in body
    assert "2026-11-03  Appellant's factum due" in body


def test_multiple_cases_subject_is_plural():
    subject, _ = format_alert_email([CASE, CASE_NO_DEADLINES])
    assert subject == "2 new Charter cases granted leave to appeal at the SCC"


def test_case_without_deadlines_gets_placeholder():
    _, body = format_alert_email([CASE_NO_DEADLINES])
    assert "not yet posted by the Registrar" in body


def test_send_email_uses_ssl_for_port_465():
    with patch("alerts.smtplib.SMTP_SSL") as ssl_cls:
        server = MagicMock()
        ssl_cls.return_value.__enter__.return_value = server
        send_email(smtp_host="smtp.gmail.com", smtp_port=465, smtp_user="me@gmail.com",
                    smtp_pass="pw", from_addr="me@gmail.com", to_addr="me@gmail.com",
                    subject="s", body="b")
        ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=30)
        server.login.assert_called_once_with("me@gmail.com", "pw")
        server.send_message.assert_called_once()


def test_send_email_uses_starttls_for_other_ports():
    with patch("alerts.smtplib.SMTP") as smtp_cls:
        server = MagicMock()
        smtp_cls.return_value.__enter__.return_value = server
        send_email(smtp_host="smtp.office365.com", smtp_port=587, smtp_user="me@osgoode.yorku.ca",
                    smtp_pass="pw", from_addr="me@osgoode.yorku.ca", to_addr="me@osgoode.yorku.ca",
                    subject="s", body="b")
        smtp_cls.assert_called_once_with("smtp.office365.com", 587, timeout=30)
        server.starttls.assert_called_once()
        server.send_message.assert_called_once()
