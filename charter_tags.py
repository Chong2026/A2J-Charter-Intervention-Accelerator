"""Tag a Charter case with the sections and doctrines it raises.

Input is the SCC Registry's "Keywords" line and the case summary from the docket
page. Two kinds of evidence are used:

1. Explicit citations of Charter sections, e.g. "s. 11(b) of the Charter",
   "Canadian Charter of Rights and Freedoms, ss. 7, 15", "section 7 Charter".
   Only section numbers tied to the word "Charter" count, so "s. 7 of the
   Status of the Artist Act" is ignored.
2. Descriptive phrases the Registry uses instead of section numbers, e.g.
   "Freedom of religion" -> s. 2(a), "Right to be tried within reasonable time"
   -> s. 11(b), "Arbitrariness" -> s. 7 (arbitrariness).

The phrase table below is a first draft written for legal review: add, remove or
correct entries as you see fit. Each entry is (tag, regular expression).
Doctrine tags are written "s. 7 – arbitrariness" so that a filter for "s. 7"
also matches them.
"""
import re

# --- Descriptive phrases -> tag --------------------------------------------
# Patterns are matched case-insensitively against keywords + summary.
PHRASES: list[tuple[str, str]] = [
    # s. 1
    ("s. 1", r"[—–-]\s*Justification\s*(?:[—–-]|\.|$)|\bdemonstrably justified\b|\breasonable limits?\b.{0,40}\bprescribed by law\b|\bOakes test\b"),
    # s. 2 fundamental freedoms
    ("s. 2(a)", r"\bfreedom of (?:religion|conscience)\b"),
    ("s. 2(b)", r"\bfreedom of (?:expression|the press|thought, belief, opinion)\b"),
    ("s. 2(c)", r"\bfreedom of (?:peaceful )?assembly\b"),
    ("s. 2(d)", r"\bfreedom of association\b"),
    # democratic and mobility rights
    ("s. 3", r"\bright to vote\b|\bdemocratic rights\b"),
    ("s. 6", r"\bmobility rights\b"),
    # s. 7 and its doctrines
    ("s. 7", r"\bright to life, liberty and security\b|\bfundamental justice\b|\bsecurity of (?:the )?person\b"),
    ("s. 7 – arbitrariness", r"\barbitrariness\b"),
    ("s. 7 – overbreadth", r"\boverbreadth\b|\boverbroad\b"),
    ("s. 7 – gross disproportionality", r"\bgross(?:ly)? disproportion"),
    ("s. 7 – vagueness", r"\bvagueness\b|\bvoid for vagueness\b|\bunconstitutionally vague\b"),
    ("s. 7 – right to silence", r"\bright to (?:remain )?silen(?:ce|t)\b"),
    ("s. 7 – full answer and defence", r"\bfull answer and defen[cs]e\b"),
    ("s. 7 – disclosure", r"\b(?:Crown|third[- ]party) (?:disclosure|records)\b|\bStinchcombe\b"),
    ("s. 7 – abuse of process", r"\babuse of process\b"),
    # legal rights
    ("s. 8", r"\bsearch(?:es)? and seizures?\b|\bunreasonable search\b|\breasonable expectation of privacy\b"),
    ("s. 9", r"\barbitrary (?:detention|imprisonment)\b|\barbitrarily (?:detained|imprisoned)\b"),
    ("s. 10(a)", r"\binformed promptly of (?:the )?reasons\b"),
    ("s. 10(b)", r"\bright to counsel\b"),
    ("s. 11(b)", r"\btried within (?:a )?reasonable time\b|\bunreasonable delay\b|\bJordan ceiling\b"),
    ("s. 11(c)", r"\btestimonial compulsion\b|\bcompelled to be a witness\b"),
    ("s. 11(d)", r"\bpresumption of innocence\b|\bpresumed innocent\b"),
    ("s. 11(e)", r"\breasonable bail\b|\bjust cause\b.{0,30}\bbail\b"),
    ("s. 11(f)", r"\bright to (?:a )?(?:trial by )?jury\b|\bbenefit of (?:a )?trial by jury\b"),
    ("s. 11(h)", r"\bdouble jeopardy\b|\btried or punished (?:for it )?again\b"),
    ("s. 11(i)", r"\bbenefit of the lesser punishment\b"),
    ("s. 12", r"\bcruel and unusual\b"),
    ("s. 13", r"\bself-incrimination\b"),
    ("s. 14", r"\bassistance of an interpreter\b"),
    # equality
    ("s. 15", r"\bright to equality\b|\bequality rights?\b|\bequal protection and (?:equal )?benefit\b"),
    # language rights
    ("s. 16–22", r"\bofficial languages?\b"),
    ("s. 23", r"\bminority language educational rights\b|\bminority language education\b"),
    # remedies and interpretive provisions
    ("s. 24(1)", r"\bCharter damages\b|\bappropriate and just\b"),
    ("s. 24(2)", r"\bexclusion of evidence\b|\bexclude(?:d)? (?:the )?evidence\b|\bbring the administration of justice into disrepute\b"),
    ("s. 25", r"\baboriginal(?:, treaty or other)? rights?.{0,40}\bnot (?:be )?construed\b"),
    ("s. 28", r"\bequally to male and female persons\b"),
    ("s. 33", r"\bnotwithstanding clause\b|\boverride clause\b"),
]

LABELS = {
    "s. 1": "reasonable limits", "s. 2(a)": "freedom of religion/conscience",
    "s. 2(b)": "freedom of expression", "s. 2(c)": "freedom of assembly",
    "s. 2(d)": "freedom of association", "s. 3": "democratic rights",
    "s. 6": "mobility rights", "s. 7": "life, liberty and security of the person",
    "s. 8": "search and seizure", "s. 9": "arbitrary detention",
    "s. 10(a)": "reasons for arrest", "s. 10(b)": "right to counsel",
    "s. 11(b)": "trial within a reasonable time", "s. 11(c)": "non-compellability",
    "s. 11(d)": "presumption of innocence", "s. 11(e)": "reasonable bail",
    "s. 11(f)": "jury trial", "s. 11(h)": "double jeopardy",
    "s. 11(i)": "lesser punishment", "s. 12": "cruel and unusual punishment",
    "s. 13": "self-incrimination", "s. 14": "interpreter", "s. 15": "equality",
    "s. 16–22": "official languages", "s. 23": "minority language education",
    "s. 24(1)": "remedies", "s. 24(2)": "exclusion of evidence",
    "s. 25": "Aboriginal rights not abrogated", "s. 28": "gender equality",
    "s. 33": "notwithstanding clause",
}

# --- Explicit citations ----------------------------------------------------
_SEC = r"\d{1,2}(?:\(\d\))?(?:\([a-z]\))?"                       # 7, 2(a), 24(2), 6(1)
_LIST = rf"{_SEC}(?:\s*(?:,|and|or|&)\s*{_SEC})*"                   # 2(a) and 15 / 7, 15
_CHARTER = r"(?:the\s+)?(?:Canadian\s+)?Charter(?:\s+of\s+Rights(?:\s+and\s+Freedoms)?)?"
_CITE_BEFORE = re.compile(rf"\b(?:ss?\.|sections?)\s*({_LIST})\s+(?:of\s+)?{_CHARTER}", re.I)
_CITE_AFTER = re.compile(rf"\bCharter(?:\s+of\s+Rights\s+and\s+Freedoms)?\s*,?\s*(?:ss?\.|sections?)\s*({_LIST})", re.I)


def _normalise(sec: str) -> str:
    """'2(a)' -> 's. 2(a)'; '6(1)' -> 's. 6'; '24(2)' stays; '11(b)' stays."""
    sec = sec.strip().lower()
    m = re.fullmatch(r"(\d{1,2})(\(\d\))?(\([a-z]\))?", sec)
    if not m:
        return ""
    num, sub_num, sub_letter = m.groups()
    if num == "24" and sub_num:                                    # 24(1) remedy vs 24(2) exclusion
        return f"s. 24{sub_num}"
    if sub_letter:
        return f"s. {num}{sub_letter}"
    return f"s. {num}"


def explicit_sections(text: str) -> set[str]:
    out = set()
    for rx in (_CITE_BEFORE, _CITE_AFTER):
        for m in rx.finditer(text):
            for part in re.split(r"\s*(?:,|and|or|&)\s*", m.group(1)):
                tag = _normalise(part)
                if tag and 1 <= int(re.match(r"s\. (\d+)", tag).group(1)) <= 34:
                    out.add(tag)
    return out


def _sort_key(tag: str):
    m = re.match(r"s\. (\d+)", tag)
    return (int(m.group(1)) if m else 99, tag)


def tag_charter_case(keywords: str, summary: str) -> list[str]:
    """Return sorted tags like ['s. 2(a)', 's. 7', 's. 7 – arbitrariness', 's. 15']."""
    text = f"{keywords}\n{summary}"
    tags = explicit_sections(text)
    for tag, pattern in PHRASES:
        if re.search(pattern, text, re.I):
            tags.add(tag)
    if any(t.startswith("s. 7 – ") for t in tags):
        tags.add("s. 7")
    return sorted(tags, key=_sort_key)


def describe(tags: list[str]) -> str:
    """'s. 2(a) freedom of religion/conscience; s. 15 equality' for emails and reports."""
    if not tags:
        return "Charter section not identified"
    return "; ".join(f"{t} {LABELS[t]}" if t in LABELS else t for t in tags)


def parse_filter(raw: str | None) -> list[str]:
    """'s.7, s 15 ,s. 7 – arbitrariness' -> ['s. 7', 's. 15', 's. 7 – arbitrariness']."""
    if not raw:
        return []
    out = []
    for item in raw.split(","):
        item = re.sub(r"\s+", " ", item.strip())
        item = re.sub(r"^(?:sections?|ss?)\.?\s*", "s. ", item, flags=re.I)
        item = item.replace(" - ", " – ")
        if item:
            out.append(item)
    return out


def matches_filter(tags: list[str], wanted: list[str]) -> bool:
    """Empty filter = everything. 's. 7' matches 's. 7 – arbitrariness'; 's. 2' matches 's. 2(b)'."""
    if not wanted:
        return True
    for w in wanted:
        for t in tags:
            if t.lower() == w.lower():
                return True
            if t.lower().startswith(w.lower()) and t[len(w):len(w) + 1] in ("(", " "):
                return True
    return False
