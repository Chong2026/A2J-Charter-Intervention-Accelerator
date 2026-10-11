"""Pure parsing functions for SCC pages (no network, no database).

Three page types are handled:
  * leave-decision item page   (decisions.scc-csc.ca/.../item/<id>/index.do?iframe=true)
  * SCC docket page            (scc-csc.ca/cases-dossiers/search-recherche/<case no>/)
  * the Registrar's scheduling letter that appears on the docket after leave is granted
"""
import re
from datetime import datetime

from bs4 import BeautifulSoup


def html_to_lines(html: str) -> list[str]:
    """Visible text of a page, one text node per line, blanks removed."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = (ln.strip() for ln in soup.get_text("\n", strip=True).splitlines())
    return [ln for ln in lines if ln]


# --------------------------------------------------------------------------
# Leave-decision item page
# --------------------------------------------------------------------------
def _after(lines: list[str], label: str):
    for i, line in enumerate(lines):
        if line == label and i + 1 < len(lines):
            return lines[i + 1]
    return None


def parse_item_lines(lines: list[str]) -> dict:
    case_no = _after(lines, "Case number")
    date = _after(lines, "Date")
    text = "\n".join(lines)
    m = re.search(r"\b(\d{4} [A-Z]{2,8} \d+)\b", text)  # e.g. 2025 ABCA 413
    return {
        "case_no": case_no if case_no and re.fullmatch(r"\d{4,6}", case_no) else None,
        "status": _after(lines, "Status"),
        "appeal_from": _after(lines, "On appeal from"),
        "decision_date": date if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else None,
        "lower_court_citation": m.group(1) if m else None,
    }


# --------------------------------------------------------------------------
# Docket page: keywords, summary, Charter flag
# --------------------------------------------------------------------------
def parse_keywords_summary(lines: list[str]) -> tuple[str, str]:
    """Return (keywords, summary). Either may be '' if not yet posted."""
    keywords = summary = ""
    try:
        k = max(i for i, ln in enumerate(lines) if ln == "Keywords")
    except ValueError:
        return keywords, summary
    s = next((i for i in range(k + 1, len(lines)) if lines[i] == "Summary"), None)
    if s is None:
        return " ".join(lines[k + 1:k + 4]), summary
    keywords = " ".join(lines[k + 1:s])
    stop = next(
        (i for i in range(s + 1, len(lines)) if lines[i] in ("Lower court rulings", "Filed documents")),
        min(len(lines), s + 12),
    )
    summary = " ".join(lines[s + 1:stop])
    return keywords, summary


def classify_charter(keywords: str, summary: str) -> tuple[int, str]:
    """(is_charter, basis). Keywords are the strongest signal."""
    if re.search(r"charter of rights", keywords, re.I):
        return 1, "keywords"
    if re.search(r"\bcharter\b", summary, re.I):
        return 1, "summary"
    return 0, ""


# --------------------------------------------------------------------------
# Registrar's scheduling letter
# --------------------------------------------------------------------------
_DATE_RE = re.compile(r"on\s*or\s*before\s+([A-Z][a-z]+)\s+(\d{1,2}),?\s*(\d{4})")
_ITEM_START = re.compile(r"^[a-z]\)\s+")
_DOCKET_DATE_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _classify_deadline(text: str) -> str:
    t = text.lower()
    if "replies" in t:
        return "reply_on_intervention_motions"
    if "response" in t and "motion" in t:
        return "response_to_intervention_motions"
    if "notice of intervention" in t:
        return "ag_notice_of_intervention"
    if "attorney general" in t and "factum" in t:
        return "ag_intervener_factum"
    if "intervener granted" in t:
        return "intervener_factum"
    if "wishing to intervene" in t:
        return "intervention_motion"
    if "notice of appeal" in t:
        return "notice_of_appeal"
    if "factum" in t:
        return "respondent_factum" if "respondent" in t else "appellant_factum"
    return "other"


def parse_schedule(lines: list[str]) -> list[dict]:
    """Extract dated deadlines from the Registrar's letter.

    The docket lists newest entries first, so if the same kind of deadline
    appears twice (e.g. an amended schedule) the first occurrence wins.
    """
    items, current = [], None
    for ln in lines:
        if _ITEM_START.match(ln):
            current = [ln]
            items.append(current)
        elif _DOCKET_DATE_LINE.match(ln):
            current = None
        elif current is not None:
            current.append(ln)

    out, seen = [], set()
    for parts in items:
        text = re.sub(r"\s+", " ", " ".join(parts))
        m = _DATE_RE.search(text)
        if not m:
            continue
        try:
            due = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
        except ValueError:
            continue
        kind = _classify_deadline(text[:m.end()])
        if kind in seen and kind != "other":
            continue
        seen.add(kind)
        out.append({"kind": kind, "due_date": due.isoformat(), "raw_text": text[:m.end()]})
    return out
