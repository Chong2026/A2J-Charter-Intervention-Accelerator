"""Measure how accurately the Monitor's Charter classifier works.

The Monitor decides whether a case is a Charter case from the "Keywords" (and,
as a fallback, the "Summary") on its SCC docket page. This script checks that
rule against cases whose answer we already know, so you can report a concrete
accuracy figure (e.g. for the January milestone review).

Two steps:

1) sample -- builds a test set and fetches each docket page (needs internet):
     * N "known Charter" cases drawn at random from the 402-case dataset
       (data/A2J_Intervenors_Full_Dataset_FIXED.csv), labelled 'charter';
     * N other dockets from the same number range that are NOT in that dataset,
       left unlabelled for you to check by hand.
   It writes data/classifier_validation.csv.

     uv run --with requests --with beautifulsoup4 --with lxml --with pandas `
         python scripts/validate_classifier.py sample --n 30

2) Open data/classifier_validation.csv in Excel. For every row whose
   manual_label is empty, read the keywords/summary columns (or open the
   docket_url) and type 'charter' or 'not' in manual_label. Rows marked
   'skip' are ignored (e.g. pages with no keywords yet). You may also correct
   any 'charter' label you disagree with. Save as CSV.

3) score -- compares the classifier with your labels and prints the figures:

     uv run --with pandas python scripts/validate_classifier.py score

Set SCC_MONITOR_CONTACT first (same as for run_monitor.py).
"""
import argparse
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = ROOT / "data" / "A2J_Intervenors_Full_Dataset_FIXED.csv"
OUTPUT = ROOT / "data" / "classifier_validation.csv"
DOCKET_URL = "https://www.scc-csc.ca/cases-dossiers/search-recherche/{}/"
COLUMNS = ["docket", "group", "manual_label", "predicted", "basis",
           "keywords", "summary", "docket_url", "fetch_error"]


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def pick_sample(known: set[int], n: int, seed: int = 2026) -> tuple[list[int], list[int]]:
    """Return (known_charter_sample, other_sample), each of size <= n.

    'other' dockets are drawn from the same number range as the known set but
    are not in it, so they are mostly non-Charter cases (to be confirmed by hand).
    """
    rng = random.Random(seed)
    known_sorted = sorted(known)
    pos = rng.sample(known_sorted, min(n, len(known_sorted)))
    lo, hi = known_sorted[0], known_sorted[-1]
    pool = [d for d in range(lo, hi + 1) if d not in known]
    neg = rng.sample(pool, min(n, len(pool)))
    return sorted(pos), sorted(neg)


def score(rows: list[dict]) -> dict:
    """rows need 'manual_label' ('charter'/'not'/other) and 'predicted' (0/1)."""
    tp = fp = fn = tn = 0
    misses, false_alarms = [], []
    for r in rows:
        label = str(r.get("manual_label", "")).strip().lower()
        if label not in ("charter", "not"):
            continue
        pred = int(r["predicted"])
        if label == "charter" and pred:
            tp += 1
        elif label == "charter":
            fn += 1
            misses.append(r["docket"])
        elif pred:
            fp += 1
            false_alarms.append(r["docket"])
        else:
            tn += 1
    total = tp + fp + fn + tn

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "labelled": total, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy": pct(tp + tn, total),
        "recall": pct(tp, tp + fn),        # share of real Charter cases the Monitor catches
        "precision": pct(tp, tp + fp),     # share of Monitor alerts that really are Charter
        "missed_dockets": misses, "false_alarm_dockets": false_alarms,
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_sample(n: int, seed: int):
    import pandas as pd
    import requests

    from scc_parse import classify_charter, html_to_lines, parse_keywords_summary

    contact = os.environ.get("SCC_MONITOR_CONTACT")
    if not contact:
        sys.exit('Set your contact email first, e.g. PowerShell:  $env:SCC_MONITOR_CONTACT = "you@example.com"')

    known = set(pd.read_csv(DATASET)["Docket_Number"].dropna().astype(int))
    pos, neg = pick_sample(known, n, seed)
    session = requests.Session()
    session.headers["User-Agent"] = f"a2aj-charter-accelerator/0.1 (research; contact: {contact})"

    rows = []
    todo = [(d, "known_charter") for d in pos] + [(d, "other") for d in neg]
    for i, (docket, group) in enumerate(todo, 1):
        url = DOCKET_URL.format(docket)
        row = {"docket": docket, "group": group,
               "manual_label": "charter" if group == "known_charter" else "",
               "predicted": "", "basis": "", "keywords": "", "summary": "",
               "docket_url": url, "fetch_error": ""}
        try:
            time.sleep(1.0)  # be polite to the SCC servers
            r = session.get(url, timeout=30)
            r.raise_for_status()
            kw, summ = parse_keywords_summary(html_to_lines(r.content.decode("utf-8", errors="replace")))
            pred, basis = classify_charter(kw, summ)
            row.update(predicted=pred, basis=basis, keywords=kw, summary=summ[:600])
            if not kw and not summ:
                row["manual_label"] = "skip"
                row["fetch_error"] = "no keywords or summary on page"
        except Exception as e:  # keep going; record the problem
            row.update(manual_label="skip", fetch_error=str(e)[:200])
        rows.append(row)
        print(f"[{i}/{len(todo)}] {docket} {group:13} predicted={row['predicted']!s:2} {row['fetch_error']}")

    pd.DataFrame(rows, columns=COLUMNS).to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"\nWrote {OUTPUT}")
    print("Next: open it in Excel, fill manual_label ('charter' / 'not') for the empty rows, save, then run 'score'.")


def cmd_score():
    import pandas as pd

    if not OUTPUT.exists():
        sys.exit(f"{OUTPUT} not found -- run the 'sample' step first.")
    df = pd.read_csv(OUTPUT, dtype=str).fillna("")
    unlabelled = df[(df["manual_label"].str.strip() == "")]
    if len(unlabelled):
        print(f"Note: {len(unlabelled)} row(s) still have no manual_label and are ignored: "
              f"{', '.join(unlabelled['docket'].head(10))}{' ...' if len(unlabelled) > 10 else ''}\n")
    rows = [r for r in df.to_dict("records") if r["predicted"] in ("0", "1")]
    s = score(rows)
    print(f"Labelled cases scored: {s['labelled']}")
    print(f"  Charter caught (true positives):   {s['tp']}")
    print(f"  Charter missed (false negatives):  {s['fn']}  {s['missed_dockets']}")
    print(f"  False alarms (false positives):    {s['fp']}  {s['false_alarm_dockets']}")
    print(f"  Correctly ignored (true negatives): {s['tn']}")
    print(f"\nAccuracy:  {s['accuracy']}%")
    print(f"Recall:    {s['recall']}%   (of real Charter cases, how many the Monitor flags)")
    print(f"Precision: {s['precision']}%   (of the Monitor's flags, how many are real Charter cases)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="build the test set and fetch docket pages")
    s.add_argument("--n", type=int, default=30, help="cases per group (default 30)")
    s.add_argument("--seed", type=int, default=2026, help="random seed, for a reproducible sample")
    sub.add_parser("score", help="compute accuracy from the labelled CSV")
    args = ap.parse_args()
    if args.cmd == "sample":
        cmd_sample(args.n, args.seed)
    else:
        cmd_score()


if __name__ == "__main__":
    main()
