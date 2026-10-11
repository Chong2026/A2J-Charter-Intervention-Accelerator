"""Tests for the pure helpers in scripts/validate_classifier.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from validate_classifier import pick_sample, score  # noqa: E402


def test_pick_sample_is_reproducible_and_disjoint():
    known = {100, 105, 110, 120, 130}
    pos1, neg1 = pick_sample(known, 3, seed=1)
    pos2, neg2 = pick_sample(known, 3, seed=1)
    assert (pos1, neg1) == (pos2, neg2)
    assert len(pos1) == 3 and set(pos1) <= known
    assert len(neg1) == 3 and not set(neg1) & known
    assert all(100 <= d <= 130 for d in neg1)


def test_pick_sample_caps_at_available():
    pos, neg = pick_sample({1, 2}, 10)
    assert pos == [1, 2] and neg == []


def test_score_counts_and_ignores_unlabelled():
    rows = [
        {"docket": "1", "manual_label": "charter", "predicted": "1"},
        {"docket": "2", "manual_label": "charter", "predicted": "0"},
        {"docket": "3", "manual_label": "not", "predicted": "1"},
        {"docket": "4", "manual_label": "not", "predicted": "0"},
        {"docket": "5", "manual_label": "Not ", "predicted": "0"},
        {"docket": "6", "manual_label": "", "predicted": "1"},
        {"docket": "7", "manual_label": "skip", "predicted": "1"},
    ]
    s = score(rows)
    assert (s["tp"], s["fn"], s["fp"], s["tn"], s["labelled"]) == (1, 1, 1, 2, 5)
    assert s["missed_dockets"] == ["2"] and s["false_alarm_dockets"] == ["3"]
    assert s["accuracy"] == 60.0 and s["recall"] == 50.0 and s["precision"] == 50.0


def test_score_empty():
    assert score([])["accuracy"] is None
