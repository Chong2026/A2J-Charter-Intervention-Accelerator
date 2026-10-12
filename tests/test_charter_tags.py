"""Tests for charter_tags, built from real SCC Registry keywords and summaries."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from charter_tags import (describe, explicit_sections, matches_filter,  # noqa: E402
                          parse_filter, tag_charter_case)

WIRRING_KW = ("Constitutional law — Charter of Rights — Freedom of religion — Justification — Legislation "
              "requiring candidates for the Alberta bar to swear or solemnly affirm oath of allegiance")
WIRRING_SUMMARY = ("Mr. Wirring issued a statement of claim challenging the requirement to take the Oath "
                   "under ss. 2(a) and 15 of the Charter.")
SUTHERLAND_KW = ("Constitutional law — Charter of Rights — Protection against testimonial compulsion — "
                 "Whether s. 11(c) of the Charter applies — Canadian Charter of Rights and Freedoms, s. 11(c).")
LYMER_KW = ("Constitutional law — Charter of Rights — Right to be tried within reasonable time — "
            "Canadian Charter of Rights and Freedoms, s. 11(b).")
G_KW = ("Charter of rights - Right to equality - Discrimination based on mental or physical disability - "
        "Whether infringement is reasonable limit demonstrably justified in free and democratic society - "
        "Canadian Charter of Rights and Freedoms, ss. 7, 15.")


def test_real_cases():
    assert tag_charter_case(WIRRING_KW, WIRRING_SUMMARY) == ["s. 1", "s. 2(a)", "s. 15"]
    assert tag_charter_case(SUTHERLAND_KW, "") == ["s. 11(c)"]
    assert tag_charter_case(LYMER_KW, "") == ["s. 11(b)"]
    assert tag_charter_case(G_KW, "") == ["s. 1", "s. 7", "s. 15"]


def test_section_7_doctrines_imply_section_7():
    kw = ("Charter of Rights — Right to life, liberty and security of person — Principles of fundamental "
          "justice — Arbitrariness — Overbreadth — Gross disproportionality")
    assert tag_charter_case(kw, "") == [
        "s. 7", "s. 7 – arbitrariness", "s. 7 – gross disproportionality", "s. 7 – overbreadth"]
    assert tag_charter_case("Charter of Rights — Vagueness", "") == ["s. 7", "s. 7 – vagueness"]


def test_explicit_citations_need_the_word_charter():
    assert explicit_sections("the s. 7 of the Status of the Artist Act") == set()
    assert explicit_sections("Canadian Charter of Rights and Freedoms, ss. 8 and 24(2).") == {"s. 8", "s. 24(2)"}
    assert explicit_sections("right guaranteed by s. 6(1) of Canadian Charter of Rights and Freedoms") == {"s. 6"}
    assert explicit_sections("infringement of an individual's section 7 Charter rights") == {"s. 7"}
    assert explicit_sections("s. 33 of the Criminal Code") == set()


def test_describe():
    assert describe(["s. 2(a)", "s. 7 – arbitrariness"]) == "s. 2(a) freedom of religion/conscience; s. 7 – arbitrariness"
    assert describe([]) == "Charter section not identified"


def test_filter_parsing_and_matching():
    assert parse_filter(" s.7, s 15 ,section 2(b), s. 7 - arbitrariness ") == [
        "s. 7", "s. 15", "s. 2(b)", "s. 7 – arbitrariness"]
    assert parse_filter("") == [] and parse_filter(None) == []
    tags = ["s. 2(a)", "s. 7 – arbitrariness"]
    assert matches_filter(tags, [])                       # no filter = everything
    assert matches_filter(tags, ["s. 7"])                 # section matches its doctrines
    assert matches_filter(tags, ["s. 2"])                 # s. 2 matches s. 2(a)
    assert matches_filter(tags, ["s. 7 – arbitrariness"])
    assert not matches_filter(tags, ["s. 7 – overbreadth"])
    assert not matches_filter(["s. 15"], ["s. 1"])        # s. 1 must not match s. 15
    assert not matches_filter([], ["s. 7"])
