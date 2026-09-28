"""Tests built from real page text copied from SCC pages (Sept 2026).

Run:  uv run --with pytest --with beautifulsoup4 --with lxml pytest
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "monitor"))

from scc_parse import (classify_charter, html_to_lines, parse_item_lines,  # noqa: E402
                       parse_keywords_summary, parse_schedule)

ITEM_ALBERTA = """
Applications for Leave
Decision Information
His Majesty the King in right of Alberta v. Prabjot Singh Wirring
Collection
Applications for Leave
Date
2026-08-06
Case number
42224
Status
Granted
On appeal from
Alberta
Notes
SCC Case Information
Decision Content
No. 42224
JUDGMENT
The application for leave to appeal from the judgment of the
Court of Appeal of Alberta (Edmonton), Number 2303-0239AC, 2025 ABCA 413, dated December 16, 2025, is granted with costs in the cause.
""".strip().splitlines()

ITEM_BC = """
Decision Information
Collection
Applications for Leave
Date
2026-07-02
Case number
42219
Status
Granted
On appeal from
British Columbia
Notes
JUDGMENT
Court of Appeal for British Columbia (Vancouver), Number CA50398, 2025 BCCA 457, dated December 19, 2025
""".strip().splitlines()

DOCKET_ALBERTA = """
Supreme Court of Canada | 42224
Docket
Parties
Counsel
Summary
Filed documents
Docket
List of proceedings
2026-09-08
Notice of appeal, (Letter Form), Completed on: 2026-09-08
His Majesty the King in right of Alberta
2026-08-07
Correspondence (sent by the Court) to, all parties;
Further to the judgment of August 6, 2026, granting leave to appeal, the schedule for serving and filing the material is set as follows:
a)       The appellant shall serve and file his notice of appealand notice of constitutional question, if any, on or before September 8, 2026.
b)      If a notice of constitutional question is filed by the appellant, any attorney general intending to intervene under subrule 33(4) of the Rules of the Supreme Court of Canada shall serve and file a notice of intervention respecting constitutional question on or before October 6, 2026.
c)      The appellant shall serve and file his factum, record and book of authorities, if any, on or before November 3, 2026.
d)      The respondent shall serve and file his factum, record and book of authorities, if any, on or before January 11, 2027.
e)      Any person wishing to intervene in this appeal under Rule 55 of the Rules of the Supreme Court of Canada shall serve and file a motion for leave to intervene on or before December 1, 2026.
f)      The appellant and respondent shall serve and file their response(s), if any, to the motions for leave to intervene on or before December 11, 2026.
g)      Replies to any responses to the motions for leave to intervene shall be served and filed on or before December 18, 2026.
h)      Any intervener granted leave to intervene under Rule 59 of the Rules of the Supreme Court of Canada shall serve and file its respective factum and book of authorities, if any, on or before February 15, 2027.
2026-08-06
Judgment on leave sent to the parties
Summary
Keywords
Constitutional law – Charter of Rights – Freedom of religion – Justification – Legislation requiring candidates for the Alberta bar to swear or solemnly affirm oath of allegiance
Summary
Mr. Wirring issued a statement of claim challenging the requirement to take the Oath under ss. 2(a) and 15 of the Charter. He sought a declaration under s. 52(1) of the Constitution Act to that effect
Lower court rulings
Filed documents
""".strip().splitlines()

DOCKET_BC = """
Supreme Court of Canada | 42219
Docket
Summary
Docket
2026-07-03
Correspondence (sent by the Court) to, all parties; by the REGISTRAR:
a)      The appellant shall serve and file her notice of appeal on or before August 31, 2026.
a)      The appellant shall serve and file her factum, record and book of authorities, if any, on or before October 13, 2026.
b)      The respondents shall serve and file their factum, record and book of authorities, if any, on or before December 8, 2026.
c)      Any person wishing to intervene in this appeal under Rule 55 of the Rules of the Supreme Court of Canada shall serve and file a motion for leave to intervene on or before November 10, 2026.
d)      The appellant and respondents shall serve and file theirresponse(s), if any, to the motions for leave to intervene on orbefore November 20, 2026.
e)      Replies to any responses to the motions for leave to intervene shall be served and filed on orbefore November 27, 2026.
f)      Any intervener granted leave to intervene under Rule 59 of the Rules of the Supreme Court of Canada shall serve and file its respective factum and book of authorities, if any, on or before January 19, 2027.
g)      The hearing date will be confirmed following a determination by the Court of its hearing schedule, and you will be advised accordingly.
2026-07-02
Copy of formal judgment sent to Registrar
Summary
Keywords
Summary
In an action initiated by the Public Guardian and Trustee on behalf of H.D., the Ministry of Children and Family Development and the Provincial Director of Child Welfare admitted liability for failing
Lower court rulings
Filed documents
""".strip().splitlines()


def test_item_pages():
    a = parse_item_lines(ITEM_ALBERTA)
    assert a == {"case_no": "42224", "status": "Granted", "appeal_from": "Alberta",
                 "decision_date": "2026-08-06", "lower_court_citation": "2025 ABCA 413"}
    b = parse_item_lines(ITEM_BC)
    assert (b["case_no"], b["appeal_from"], b["lower_court_citation"]) == ("42219", "British Columbia", "2025 BCCA 457")


def test_charter_flag_from_keywords():
    kw, summ = parse_keywords_summary(DOCKET_ALBERTA)
    assert "Charter of Rights" in kw and summ.startswith("Mr. Wirring")
    assert "Lower court" not in summ
    assert classify_charter(kw, summ) == (1, "keywords")


def test_non_charter_case_with_empty_keywords():
    kw, summ = parse_keywords_summary(DOCKET_BC)
    assert kw == "" and summ.startswith("In an action initiated")
    assert classify_charter(kw, summ) == (0, "")


def test_charter_flag_falls_back_to_summary():
    assert classify_charter("", "Challenge under s. 8 of the Charter") == (1, "summary")


def test_schedule_alberta():
    got = {d["kind"]: d["due_date"] for d in parse_schedule(DOCKET_ALBERTA)}
    assert got == {
        "notice_of_appeal": "2026-09-08",
        "ag_notice_of_intervention": "2026-10-06",
        "appellant_factum": "2026-11-03",
        "respondent_factum": "2027-01-11",
        "intervention_motion": "2026-12-01",
        "response_to_intervention_motions": "2026-12-11",
        "reply_on_intervention_motions": "2026-12-18",
        "intervener_factum": "2027-02-15",
    }


def test_schedule_bc_handles_missing_spaces_and_undated_items():
    got = {d["kind"]: d["due_date"] for d in parse_schedule(DOCKET_BC)}
    assert got == {
        "notice_of_appeal": "2026-08-31",
        "appellant_factum": "2026-10-13",
        "respondent_factum": "2026-12-08",
        "intervention_motion": "2026-11-10",
        "response_to_intervention_motions": "2026-11-20",
        "reply_on_intervention_motions": "2026-11-27",
        "intervener_factum": "2027-01-19",
    }


def test_html_to_lines_roundtrip():
    html = "<html><body><h2>Keywords</h2><p>Constitutional law – Charter of Rights</p><script>x()</script></body></html>"
    assert html_to_lines(html) == ["Keywords", "Constitutional law – Charter of Rights"]
