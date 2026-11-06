"""Exploratory fixed-capacity screening using only three frozen aggregate tables."""
import argparse
import csv
from fractions import Fraction as F
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path

NAMES = {
    "x06": "X06_TRANSITION_GROUP_DECOMPOSITION.csv",
    "x07": "X07_ALL_MONOTONE_CUTPOINT_CLASSIFICATION.csv",
    "x04": "X04_LOW_PERFORMANCE_THRESHOLD_GRID.csv",
}
EXPECTED_INPUT_SHA256 = {
    "X04_LOW_PERFORMANCE_THRESHOLD_GRID.csv": "7069e707e0b380e19c2a71c5d70c486a0612763c349dda9e45d9502aebb0e21d",
    "X06_TRANSITION_GROUP_DECOMPOSITION.csv": "b523df3653b407acbe6e56772b01605c5232530f484b776ac41fb631f232c83e",
    "X07_ALL_MONOTONE_CUTPOINT_CLASSIFICATION.csv": "4fb38483aacf0d8b327634b8fc88c1dc18555c3e1e656e1d51c5bb442053af7d",
}
BINARY = {(1,): "Digital", (2,): "Platform or mobile", (3,): "Specialised", (4,): "Integrated"}
FULL = (1, 2, 3, 4)
BLIND = ()
ILLUSTRATIVE = tuple(F(x) for x in (".20", ".35", ".50", ".75"))
TOL = F("0.000000000001")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def near(actual, expected, label):
    require(abs(actual - expected) <= TOL, "Aggregate parity failed for " + label)


def load(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def classification_rows(rows, keys):
    data = {}
    for r in rows:
        key = F(r["low_performance_quantile"]), int(r["cut_state"]) - 1
        require(key not in data, "Duplicate classification cell")
        data[key] = r
    require(data.keys() == keys, "Unexpected event-cut grid")
    return data


def archived_state_data(rows):
    state_rows = [r for r in rows if r["group_id"].startswith("state_")]
    require([r["group_id"] for r in state_rows] == [f"state_{i}" for i in range(1, 6)],
            "Expected the five ordered unique X06 states")
    require(sum(int(r["unweighted_n"]) for r in state_rows) == 14412, "Unexpected population")
    weight = [F(r["weighted_total"]) for r in state_rows]
    rate = [F(r["weighted_low_performance_share"]) for r in state_rows]
    require(all(w > 0 for w in weight) and all(0 <= p <= 1 for p in rate), "Invalid mass or risk")
    mass = [w / sum(weight) for w in weight]
    return mass, [w * p for w, p in zip(mass, rate)]


def grouped(mass, events, cut):
    edges = (0, *cut, len(mass))
    return [(sum(mass[a:b]), sum(events[a:b])) for a, b in zip(edges, edges[1:])]


def case_mass(blocks, quota):
    require(0 <= quota <= 1, "Capacity is outside the allowed range")
    remaining = quota
    total = F(0)
    for mass, cases in blocks:
        take = min(remaining, mass)
        total += take * cases / mass
        remaining -= take
    require(remaining == 0, "Capacity is outside the allowed range")
    return total


def contact_probabilities(blocks, cut, quota):
    edges = (0, *cut, 5)
    probabilities = []
    remaining = quota
    for (mass, _), left, right in zip(blocks, edges, edges[1:]):
        take = min(remaining, mass)
        probabilities.extend([take / mass] * (right - left))
        remaining -= take
    return probabilities


def format_number(value):
    return "" if value is None else format(float(value), ".12f")


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow([format_number(x) if isinstance(x, F) or x is None else x for x in row])


def partition_label(cut):
    if cut == FULL:
        return "Five states"
    if cut == BLIND:
        return "Population lottery"
    if cut in BINARY:
        return BINARY[cut]
    edges = (0, *cut, 5)
    return "|".join("".join(str(s) for s in range(a + 1, b + 1)) for a, b in zip(edges, edges[1:]))


def check_primary(mass, events, rows):
    prevalence = sum(events)
    for i in range(1, 5):
        r = rows[F(".20"), i]
        q, t = sum(mass[:i]), sum(events[:i])
        recall, fpr = t / prevalence, (q - t) / (1 - prevalence)
        measures = {
            "target_share": q, "low_performance_share": prevalence,
            "recall": recall, "specificity": 1 - fpr, "positive_predictive_value": t / q,
            "balanced_error_rate": (1 - recall + fpr) / 2,
        }
        for name, expected in measures.items():
            near(F(r[name]), expected, f"X07 {i} {name}")


def binary_envelope(blocks, knots):
    def differences(left, right, a, b):
        return (case_mass(blocks[a], left) - case_mass(blocks[b], left),
                case_mass(blocks[a], right) - case_mass(blocks[b], right))

    grid = set(knots)
    for left, right in zip(knots, knots[1:]):
        for a, b in combinations(BINARY, 2):
            dl, dr = differences(left, right, a, b)
            if dl * dr < 0:
                grid.add(left + (right - left) * dl / (dl - dr))
    grid = sorted(grid)
    spans = []
    for left, right in zip(grid, grid[1:]):
        mid = (left + right) / 2
        scores = {p: case_mass(blocks[p], mid) for p in BINARY}
        winners = tuple(p for p in BINARY if scores[p] == max(scores.values()))
        if spans and spans[-1][2] == winners:
            spans[-1] = (spans[-1][0], right, winners)
        else:
            spans.append((left, right, winners))
    return grid, spans


def sensitivity(out, mass, primary, x04, quotas):
    rows = []
    worst = {}
    for tau in sorted({tau for tau, _ in x04}):
        r = {i: x04[tau, i] for i in (1, 3, 4)}
        prevalence = F(r[1]["low_performance_share"])
        prefix = {}
        for i, item in r.items():
            near(F(item["target_share"]), sum(mass[:i]), f"X04 {tau} capacity at {i}")
            near(F(item["low_performance_share"]), prevalence, f"X04 {tau} prevalence at {i}")
            prefix[i] = prevalence * F(item["recall"])
            near(F(item["positive_predictive_value"]), prefix[i] / sum(mass[:i]),
                 f"X04 {tau} precision at {i}")
        e23 = prefix[3] - prefix[1]
        lower = max(F(0), e23 - mass[2])
        upper = min(mass[1], e23)
        require(lower <= upper, "X04 does not admit a split of the middle event mass")
        common = (prefix[1], prefix[4] - prefix[3], prevalence - prefix[4])
        allocations = [[common[0], e2, e23 - e2, common[1], common[2]] for e2 in (lower, upper)]
        require(all(0 <= e <= w for ev in allocations for e, w in zip(ev, mass)), "X04 mass infeasible")
        if tau == F(".20"):
            for i in (1, 3, 4):
                near(prefix[i], sum(primary[:i]), f"X04 primary case mass {i}")
            allocations = [primary, primary]
        observed = (BLIND, (1,), (3,), (4,), (1, 3, 4), (1, 3))
        known = {p: grouped(mass, allocations[0], p) for p in observed}
        extreme = [grouped(mass, ev, FULL) for ev in allocations]
        gaps = []
        for q in quotas:
            low, high = sorted(case_mass(b, q) for b in extreme)
            scores = [case_mass(known[p], q) * 100 for p in observed]
            if tau != F(".20"):
                require(low * 100 <= scores[-2] <= high * 100, "Four-block curve outside bounds")
            if q:
                gaps.append((high * 100 - scores[-1]) / q)
            rows.append((tau, q, *scores, low * 100, high * 100))
        worst[format(float(tau), ".2f")] = float(max(gaps))
    write_csv(out / "outcome_sensitivity.csv",
              ("nominal_event_quantile", "coverage", "lottery_cases", "digital_cases", "specialised_cases",
               "integrated_cases", "four_block_cases", "three_block_cases", "ordinal_cases_lower",
               "ordinal_cases_upper"), rows)
    return worst


def run(inputs, out):
    paths = {k: inputs / name for k, name in NAMES.items()}
    inventory = {}
    for line in (inputs / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name not in inventory, "Duplicate manifest entry")
        inventory[name] = digest
    require(set(inventory) == set(NAMES.values()),
            "Unexpected aggregate manifest")
    require(inventory == EXPECTED_INPUT_SHA256, "Input digest manifest does not match the frozen archive")
    inventory = EXPECTED_INPUT_SHA256.copy()
    for path in paths.values():
        require(sha256(path.read_bytes()).hexdigest() == EXPECTED_INPUT_SHA256[path.name], "Input digest mismatch")
    mass, events = archived_state_data(load(paths["x06"]))
    check_primary(mass, events, classification_rows(load(paths["x07"]), {(F(".20"), i) for i in range(1, 5)}))
    x04 = classification_rows(load(paths["x04"]), {(F(t), i) for t in (".10", ".15", ".20", ".25", ".30") for i in (1, 3, 4)})
    partitions = [p for n in range(5) for p in combinations(FULL, n)]
    blocks = {p: grouped(mass, events, p) for p in partitions}
    knots = [sum(mass[:i]) for i in range(6)]
    grid, spans = binary_envelope(blocks, knots)
    quotas = sorted(set(grid) | set(ILLUSTRATIVE) | {F(i, 100) for i in range(101)})
    prevalence = sum(events)
    out.mkdir(parents=True, exist_ok=False)

    def record(p, q):
        t = case_mass(blocks[p], q)
        return (partition_label(p), len(p) + 1, q, 100*t, 100*t/q if q else None, t/prevalence,
                100*(case_mass(blocks[FULL], q) - t))

    for p in partitions:
        near(case_mass(blocks[p], F(1)), prevalence, f"end point {p}")
        require(all(case_mass(blocks[p], q) <= min(q, prevalence) for q in quotas), f"Impossible yield {p}")
    write_csv(out / "capacity_curves.csv",
              ("rule", "blocks", "coverage", "cases_per_100_eligible", "cases_per_100_contacts",
               "recall", "loss_vs_five_states_per_100_eligible"),
              (record(p, q) for q in quotas for p in partitions))
    write_csv(out / "illustrative_quotas.csv",
              ("rule", "blocks", "coverage", "cases_per_100_eligible", "cases_per_100_contacts",
               "recall", "loss_vs_five_states_per_100_eligible"),
              (record(p, q) for q in ILLUSTRATIVE for p in (FULL, *BINARY, BLIND)))
    write_csv(out / "best_binary_intervals.csv", ("coverage_from", "coverage_to", "interior_best_binary"),
              ((a, b, "|".join(map(partition_label, p))) for a, b, p in spans))
    merge = []
    for i in FULL:
        p = tuple(k for k in FULL if k != i)
        losses = [100*(case_mass(blocks[FULL], q) - case_mass(blocks[p], q)) for q in knots]
        merge.append((f"{i}+{i+1}", partition_label(p), min(losses), max(losses), knots[losses.index(max(losses))]))
    write_csv(out / "adjacent_merges.csv",
              ("states_merged", "rule", "min_loss_per_100_eligible", "max_loss_per_100_eligible",
               "first_quota_at_max_loss"), merge)
    worst_loss = {
        p: max(100 * (case_mass(blocks[FULL], q) - case_mass(blocks[p], q)) / q for q in knots[1:])
        for p in partitions
    }
    write_csv(out / "compression_profiles.csv", ("blocks", "rule", "worst_loss_per_100_contacts",
                                                "minimax_within_block_count"),
              ((len(p) + 1, partition_label(p), worst_loss[p],
                int(worst_loss[p] == min(worst_loss[x] for x in partitions if len(x) == len(p))))
               for p in partitions))
    composition, displacement = [], []
    for q in ILLUSTRATIVE:
        reference = contact_probabilities(blocks[FULL], FULL, q)
        for p in (FULL, *BINARY, BLIND):
            probabilities = contact_probabilities(blocks[p], p, q)
            selected = [w * a for w, a in zip(mass, probabilities)]
            require(sum(selected) == q, "Composition does not meet expected capacity")
            require(sum(e * a for e, a in zip(events, probabilities)) == case_mass(blocks[p], q),
                    "Composition and total case mass disagree")
            displacement.append((partition_label(p), q,
                                 50 * sum(w * abs(a - b) for w, a, b in zip(mass, probabilities, reference)) / q))
            composition.extend((partition_label(p), q, i + 1, a, 100 * t / q, 100 * a * e / q)
                               for i, (a, t, e) in enumerate(zip(probabilities, selected, events)))
    write_csv(out / "list_composition.csv", ("rule", "coverage", "state", "contact_probability",
                                            "share_of_expected_contacts_percent",
                                            "cases_per_100_contacts_from_state"), composition)
    write_csv(out / "list_composition_distance.csv", ("rule", "coverage", "state_mix_distance_per_100_contacts"),
              displacement)
    worst_sensitivity = sensitivity(out, mass, events, x04, quotas)
    max_gap, peak = max((100*(case_mass(blocks[FULL], q) - max(case_mass(blocks[p], q) for p in BINARY)), q) for q in grid)
    receipt = {
        "scope": "Retrospective exploratory point estimates on frozen weighted aggregates",
        "input_sha256": inventory, "unweighted_n": 14412,
        "realised_prevalence": float(prevalence), "x07_numeric_parity_checks": 24,
        "partitions": len(partitions), "coverage_grid_points": len(quotas),
        "largest_ordinal_minus_best_binary_cases_per_100_eligible": float(max_gap),
        "coverage_at_largest_gap": float(peak),
        "at_50_cases_per_100_contacts": {partition_label(p): float(record(p, F(".50"))[4])
                                       for p in (FULL, *BINARY, BLIND)},
        "three_block_upper_loss_per_100_contacts_by_event_quantile": worst_sensitivity,
        "microdata_accessed": False, "confidence_intervals_computed": False,
        "best_binary_is_retrospective": True,
    }
    (out / "result_summary.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.inputs, a.output)
