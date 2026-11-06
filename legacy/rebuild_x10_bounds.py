#!/usr/bin/env python3
"""Bound fixed-coverage binary recall on retained mixtures from frozen X10 ranges."""
import argparse
import csv
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path

ARCHIVE_SHA256 = "b0d693b2807f008f71f7aa67786c0dd073831d2635b8e7e3a74a12884f3a834a"
INPUT = "X10_LEAVE_ONE_SOURCE_OUT_CLASSIFICATION_RANGES.csv"
DIGITAL = "digitally_enabled_planning"
SPECIALISED = "specialised_planning"
INTEGRATED = "integrated_planning"
BOUNDARIES = (DIGITAL, SPECIALISED, INTEGRATED)
QUOTAS = tuple(map(F, ("0", "0.20", "0.35", "0.50", "0.75", "1")))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def recall_at_quota(q, target_share, recall):
    """Apply equal contact probabilities within each binary priority group."""
    if q <= target_share:
        return q * recall / target_share
    return recall + (q - target_share) * (1 - recall) / (1 - target_share)


def load_corners(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("X10 input does not match the frozen SHA-256")
    corners = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["boundary"]
            s0, s1, r0, r1 = (F(row[key]) for key in (
                "target_share_min", "target_share_max", "recall_min", "recall_max"
            ))
            if row["omissions"] != "12" or name in corners:
                raise ValueError("Unexpected X10 boundary or deletion count")
            if not (0 < s0 <= s1 < 1 and 0 <= r0 <= r1 <= 1):
                raise ValueError("X10 ranges outside the probability domain")
            corners[name] = ((s1, r0), (s0, r1))
    if set(corners) != set(BOUNDARIES):
        raise ValueError("Missing or unexpected X10 boundary")
    return corners


def strict_support(lower, upper):
    """Find positive intervals by intersecting two piecewise-linear corners."""
    cuts = sorted({F(0), lower[0], upper[0], F(1)})

    def gap(q):
        return recall_at_quota(q, *lower) - recall_at_quota(q, *upper)

    roots = []
    for left, right in zip(cuts, cuts[1:]):
        a, b = gap(left), gap(right)
        if a * b < 0:
            roots.append(left - a * (right - left) / (b - a))
    cuts = sorted(set(cuts + roots))
    intervals = []
    for left, right in zip(cuts, cuts[1:]):
        if gap((left + right) / 2) > 0:
            if intervals and intervals[-1][1] == left and gap(left) > 0:
                intervals[-1] = (intervals[-1][0], right)
            else:
                intervals.append((left, right))
    return intervals


def compute(corners):
    quota_rows = []
    for q in QUOTAS:
        bounds = {
            name: tuple(recall_at_quota(q, *corner) for corner in corners[name])
            for name in BOUNDARIES
        }
        for name, (lo, hi) in bounds.items():
            if not 0 <= lo <= hi <= 1:
                raise ValueError("Invalid quota bounds")
            quota_rows.append({
                "coverage": float(q),
                "boundary": name,
                "recall_lower": float(lo),
                "recall_upper": float(hi),
            })
    comparisons = {}
    for name in (SPECIALISED, INTEGRATED):
        support = strict_support(corners[DIGITAL][0], corners[name][1])
        comparisons[name] = {
            "strict_coverage_intervals_open": [[float(a), float(b)] for a, b in support],
            "intervals_exact": [[str(a), str(b)] for a, b in support],
            "lower_bound_for_digital_minus_comparator_recall": {
                str(float(q)): float(
                    recall_at_quota(q, *corners[DIGITAL][0])
                    - recall_at_quota(q, *corners[name][1])
                )
                for q in QUOTAS
            },
        }
    return quota_rows, comparisons


def qa(corners, comparisons):
    for lower, upper in corners.values():
        for step in range(101):
            q = F(step, 100)
            lo, hi = recall_at_quota(q, *lower), recall_at_quota(q, *upper)
            for i in range(6):
                s = upper[0] + F(i, 5) * (lower[0] - upper[0])
                for j in range(6):
                    r = lower[1] + F(j, 5) * (upper[1] - lower[1])
                    require(lo <= recall_at_quota(q, s, r) <= hi, "Corner bounds fail the parameter-grid check")
            if q in (0, 1):
                require(lo == hi == q, "Recall bounds do not tie at an endpoint")
    for comparator, result in comparisons.items():
        intervals = [(F(a), F(b)) for a, b in result["intervals_exact"]]
        for step in range(1001):
            q = F(step, 1000)
            gap = recall_at_quota(q, *corners[DIGITAL][0]) - recall_at_quota(
                q, *corners[comparator][1]
            )
            require((gap > 0) == any(a < q < b for a, b in intervals), "Strict interval disagrees with the quota grid")
        for a, b in intervals:
            for q in (a, b):
                require(recall_at_quota(q, *corners[DIGITAL][0]) == recall_at_quota(
                    q, *corners[comparator][1]
                ), "Recall does not tie at a strict-interval boundary")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name(INPUT))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    corners = load_corners(args.input)
    quota_rows, comparisons = compute(corners)
    qa(corners, comparisons)
    args.output_dir.mkdir()
    with (args.output_dir / "X10_FIXED_CAPACITY_RECALL_BOUNDS.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(quota_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(quota_rows)
    result = {
        "input_sha256": ARCHIVE_SHA256,
        "retained_mixtures": 12,
        "comparisons": comparisons,
        "qa": {
            "status": "PASS",
            "quota_grid_points_for_corner_dominance": 101,
            "parameter_grid_per_corner_check": [6, 6],
            "quota_grid_points_for_strict_intervals": 1001,
            "endpoints": "All rules tie at both zero and full coverage",
        },
        "scope": "Conservative deterministic bounds on event recall within each retained mixture",
        "unresolved": "Outside strict intervals the independent ranges do not establish ordering",
    }
    (args.output_dir / "X10_FIXED_CAPACITY_QA.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
