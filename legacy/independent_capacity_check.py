#!/usr/bin/env python3
"""Independent Decimal check using archived aggregate policy endpoints."""
from argparse import ArgumentParser
from collections import defaultdict
from csv import DictReader
from decimal import Decimal, getcontext
from hashlib import sha256
from itertools import combinations
from json import dumps
from pathlib import Path

getcontext().prec = 42
D = Decimal
ZERO = D(0)
ONE = D(1)
HUNDRED = D(100)
TOL = D("1e-14")
QUOTAS = tuple(map(D, ("0.20", "0.35", "0.50", "0.75")))
CUTS = {
    1: "digital",
    2: "platform/mobile-or-better",
    3: "specialised",
    4: "integrated",
}


def require_close(value, reference, label):
    if abs(value - reference) > TOL:
        raise ValueError(f"{label}: {value} != {reference}")


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(DictReader(handle))


def knots(masses, events, cuts):
    positions = (0, *cuts, len(masses))
    return [
        (ONE if index == len(masses) else sum(masses[:index]), sum(events[:index]))
        for index in positions
    ]


def event_mass(points, quota):
    """Read a polyline segment from policy endpoint totals."""
    for (left, low), (right, high) in zip(points, points[1:]):
        if quota <= right + D("1e-38"):
            return low + (quota - left) * (high - low) / (right - left)
    raise ValueError(f"Quota outside archived curve: {quota}")


def labelled(cuts):
    spans = zip((0, *cuts), (*cuts, 5))
    return "|".join("".join(str(k + 1) for k in range(l, r)) for l, r in spans)


def precision(points, quota):
    return event_mass(points, quota) / quota * HUNDRED


def crossings(left, right):
    """All interior, non-tangent intersections between two archived curves."""
    shared = sorted({x for x, _ in left + right})
    for low, high in zip(shared, shared[1:]):
        a = event_mass(left, low) - event_mass(right, low)
        b = event_mass(left, high) - event_mass(right, high)
        if a * b < 0:
            yield low + (high - low) * a / (a - b)


def envelope(binaries):
    """Ranges for the ex-post best binary, a diagnostic, not an implementable rule."""
    breaks = {x for curve in binaries.values() for x, _ in curve}
    for a, b in combinations(binaries.values(), 2):
        breaks.update(crossings(a, b))
    result = []
    edges = sorted(breaks)
    for lo, hi in zip(edges, edges[1:]):
        mid = (lo + hi) / 2
        winner = max(binaries, key=lambda name: event_mass(binaries[name], mid))
        if result and result[-1][2] == winner:
            result[-1] = (result[-1][0], hi, winner)
        else:
            result.append((lo, hi, winner))
    return result


def verify_x07(path, masses, events):
    rows = table(path)
    if len(rows) != 4 or {int(r["cut_state"]) for r in rows} != {2, 3, 4, 5}:
        raise ValueError("Unexpected primary X07 cut universe.")
    prevalence = sum(events)
    for row in rows:
        cut = int(row["cut_state"]) - 1
        capacity = sum(masses[:cut])
        selected_events = sum(events[:cut])
        tpr = selected_events / prevalence
        fpr = (capacity - selected_events) / (ONE - prevalence)
        for key, value in (
            ("target_share", capacity),
            ("low_performance_share", prevalence),
            ("recall", tpr),
            ("positive_predictive_value", selected_events / capacity),
            ("false_positive_rate", fpr),
            ("balanced_error_rate", (ONE - tpr + fpr) / 2),
        ):
            require_close(D(row[key]), value, f"X07 {cut} {key}")
    return {"verified_cuts": 4, "metrics_per_cut": 6, "absolute_tolerance": TOL}


def reconstruct_x04(path, masses):
    by_threshold = defaultdict(dict)
    for row in table(path):
        nominal = D(row["low_performance_quantile"])
        cut = int(row["cut_state"]) - 1
        if cut in by_threshold[nominal]:
            raise ValueError(f"Repeated X04 cut: {nominal}, {cut}")
        by_threshold[nominal][cut] = row

    out = {}
    for nominal, group in sorted(by_threshold.items()):
        if set(group) != {1, 3, 4}:
            raise ValueError(f"Unexpected X04 boundaries at {nominal}.")
        p = D(group[1]["low_performance_share"])
        cumul = {}
        for cut, row in sorted(group.items()):
            q = sum(masses[:cut])
            require_close(D(row["target_share"]), q, "X04 state weight")
            require_close(D(row["low_performance_share"]), p, "X04 prevalence")
            cumul[cut] = D(row["target_share"]) * D(row["positive_predictive_value"])
            require_close(cumul[cut], p * D(row["recall"]), "X04 endpoint parity")
        m2, m3 = masses[1:3]
        e23 = cumul[3] - cumul[1]
        e2_low = max(ZERO, e23 - m3)
        e2_high = min(m2, e23)
        options = []
        for e2 in (e2_low, e2_high):
            events = (cumul[1], e2, e23 - e2, cumul[4] - cumul[3], p - cumul[4])
            options.append(knots(masses, events, (1, 2, 3, 4)))
        coarsened = [options[0][i] for i in (0, 1, 3, 4, 5)]
        three_blocks = [options[0][i] for i in (0, 1, 3, 5)]
        max_three_block_gap = max(
            precision(candidate, q) - precision(three_blocks, q)
            for candidate in options
            for q, _ in candidate[1:]
        )
        lo = min(precision(c, D("0.5")) for c in options)
        hi = max(precision(c, D("0.5")) for c in options)
        out[str(nominal)] = {
            "prevalence": p,
            "q50_precision_binary_and_blind": {
                **{
                    CUTS[cut]: precision([(ZERO, ZERO), (sum(masses[:cut]), endpoint), (ONE, p)], D("0.5"))
                    for cut, endpoint in cumul.items()
                },
                "blind": p * HUNDRED,
            },
            "q50_precision_four_blocks": precision(coarsened, D("0.5")),
            "q50_precision_three_blocks_1_23_45": precision(three_blocks, D("0.5")),
            "max_possible_three_block_precision_loss_over_all_quotas_using_x04_alone": max_three_block_gap,
            "q50_precision_full_five_state_bounds_using_x04_alone": [lo, hi],
        }
    return out


def audit(x06, x07, x04):
    source = [
        row for row in table(x06) if row["group_id"] in {f"state_{i}" for i in range(1, 6)}
    ]
    source.sort(key=lambda row: row["group_id"])
    if [row["group_id"] for row in source] != [f"state_{i}" for i in range(1, 6)]:
        raise ValueError("X06 must have exactly five unique states.")
    weights = [D(row["weighted_total"]) for row in source]
    risks = [D(row["weighted_low_performance_share"]) for row in source]
    if not all(w > 0 and 0 <= p <= 1 for w, p in zip(weights, risks)):
        raise ValueError("Invalid X06 mass or event proportion.")
    masses = [w / sum(weights) for w in weights]
    events = [w * p for w, p in zip(masses, risks)]
    full_cuts = (1, 2, 3, 4)
    full = knots(masses, events, full_cuts)
    grid = [q for q, _ in full][1:]
    groups = {
        cuts: knots(masses, events, cuts)
        for size in range(5)
        for cuts in combinations(full_cuts, size)
    }
    if len(groups) != 16 or len({labelled(cuts) for cuts in groups}) != 16:
        raise ValueError("Partition enumeration mismatch.")
    binary = {CUTS[cut]: groups[(cut,)] for cut in full_cuts}
    dominance_gap = min(
        event_mass(full, q) - event_mass(curve, q)
        for q in grid
        for curve in groups.values()
    )
    require_close(dominance_gap, ZERO, "Full registry dominance on all knots")
    # Synthetic non-monotone state risks, with fixed technology order, falsify structural dominance.
    toy_weights = (D("0.3"), D("0.3"), D("0.4"))
    toy_events = (D("0.03"), D("0.24"), D("0.02"))
    toy_q = D("0.2")
    toy_full = precision(knots(toy_weights, toy_events, (1, 2)), toy_q)
    toy_merged = precision(knots(toy_weights, toy_events, (2,)), toy_q)
    if toy_merged <= toy_full:
        raise ValueError("Synthetic dominance counterexample did not materialise.")

    # Between common knots the event-mass gap is linear and its ratio to
    # coverage is monotone or constant. Include all positive knots.
    maximum_precision_losses = {
        labelled(cuts): max(
            precision(full, q) - precision(curve, q)
            for q in grid
        )
        for cuts, curve in groups.items()
    }
    merges = {}
    for omit in full_cuts:
        reduced = tuple(c for c in full_cuts if c != omit)
        curve = groups[reduced]
        quota_at_loss = full[omit][0]
        maximum_gap = precision(full, quota_at_loss) - precision(curve, quota_at_loss)
        if any(precision(full, q) - precision(curve, q) > maximum_gap + TOL for q in grid):
            raise ValueError("Merge-gap maximum does not agree across knots.")
        merges[labelled(reduced)] = {
            "removed_cut": omit,
            "gap_at_quotas": {
                str(q): precision(full, q) - precision(curve, q) for q in QUOTAS
            },
            "max_gap_quota": quota_at_loss,
            "max_gap_cases_per_100_contacts": maximum_gap,
            "max_gap_cases_per_100_population": (
                event_mass(full, quota_at_loss) - event_mass(curve, quota_at_loss)
            ) * HUNDRED,
        }
    return {
        "source_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in (x06, x07, x04)},
        "weighted_total": sum(weights),
        "unweighted_n": sum(int(r["unweighted_n"]) for r in source),
        "prevalence": sum(events),
        "state_event_rates": risks,
        "state_masses": masses,
        "x07_parity": verify_x07(x07, masses, events),
        "precision_cases_per_100_contacts": {
            str(q): {labelled(cuts): precision(curve, q) for cuts, curve in groups.items()}
            for q in QUOTAS
        },
        "binary_ex_post_envelope": envelope(binary),
        "max_precision_loss_by_partition": maximum_precision_losses,
        "adjacent_single_merges": merges,
        "minimum_full_registry_advantage_over_all_partitions_at_knots": dominance_gap,
        "synthetic_counterexample": {"q": toy_q, "full": toy_full, "merged": toy_merged},
        "x04_sensitivity": reconstruct_x04(x04, masses),
        "scope": [
            "Expected weighted capacity and event mass, with a uniform lottery inside the marginal block.",
            "X04 identifies three binary curves, blind and the four-block curve 1|23|4|5. "
            "At non-primary thresholds it leaves state 2/3 event masses unidentified; "
            "marginal bounds use X04 totals and X06 weights only. At the primary threshold, use X06 for the five-state point.",
            "Point estimates only. No joint survey replicates, causal claim, raw microdata or realised operation.",
        ],
    }


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("aggregate_inputs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(
        args.aggregate_inputs / "X06_TRANSITION_GROUP_DECOMPOSITION.csv",
        args.aggregate_inputs / "X07_ALL_MONOTONE_CUTPOINT_CLASSIFICATION.csv",
        args.aggregate_inputs / "X04_LOW_PERFORMANCE_THRESHOLD_GRID.csv",
    )
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(dumps(result, indent=2, default=str) + "\n")
