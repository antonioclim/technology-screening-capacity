"""Gated source-held-out comparison using only source-by-state aggregates."""
import argparse
import csv
from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
import io
import json
from pathlib import Path
import re
from statistics import median

QUOTAS = tuple(map(F, (".20", ".35", ".50", ".75")))
BINARY = {
    "digital": (1,),
    "platform_or_mobile": (2,),
    "specialised": (3,),
    "integrated": (4,),
}
FIXED = {"five_states": (1, 2, 3, 4), **BINARY, "population_lottery": ()}
FIELDS = ("source", "state", "n", "n_cases", "weight_mass", "case_mass")
SOURCE_COUNT = 12
FROZEN_N = 14412
MIN_CELL = 20
WEIGHT_TOL = F("0.00000001")
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}")
COUNT = re.compile(r"[0-9]{1,5}")
MASS = re.compile(r"[0-9]{1,8}(?:\.[0-9]{1,24})?")


@dataclass(frozen=True)
class Cell:
    n: int
    n_cases: int
    weight: F
    cases: F


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_csv(payload):
    """Use neutral diagnostics so invalid input never leaks field contents."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
    require(tuple(reader.fieldnames or ()) == FIELDS, "Unexpected CSV header")
    data = {}
    for row in reader:
        require(None not in row and all(isinstance(row[k], str) for k in FIELDS),
                "Invalid CSV row width")
        source, state, n, n_cases, weight, cases = (row[k] for k in FIELDS)
        require(TOKEN.fullmatch(source) and state in "12345" and len(state) == 1,
                "Invalid source token or state code")
        require(COUNT.fullmatch(n) and COUNT.fullmatch(n_cases)
                and MASS.fullmatch(weight) and MASS.fullmatch(cases), "Invalid aggregate field")
        cells = data.setdefault(source, {})
        state = int(state)
        require(state not in cells, "Duplicate source/state cell")
        cells[state] = Cell(int(n), int(n_cases), F(weight), F(cases))
    require(all(set(cells) == set(range(1, 6)) for cells in data.values()),
            "Each source requires exactly five explicit state cells")
    return [tuple(cells[i] for i in range(1, 6)) for cells in data.values()]


def validate(sources, synthetic):
    require(len(sources) == SOURCE_COUNT, "Unexpected source count")
    require(all(len(cells) == 5 for cells in sources), "Unexpected state count")
    for cells in sources:
        for c in cells:
            require(0 <= c.n_cases <= c.n and 0 <= c.cases <= c.weight,
                    "Infeasible aggregate cell")
            require((c.n == 0) == (c.weight == 0)
                    and (c.n_cases == 0) == (c.cases == 0)
                    and (c.n_cases == c.n) == (c.cases == c.weight),
                    "Counts and weighted masses disagree on support")
        n = sum(c.n for c in cells)
        e = sum(c.n_cases for c in cells)
        require(n >= MIN_CELL and 0 < e < n, "Source lacks the minimum sample or event support")
        require(abs(sum(c.weight for c in cells) - n) <= WEIGHT_TOL * n,
                "Source weights are not normalised to its count")
    if not synthetic:
        require(sum(c.n for cells in sources for c in cells) == FROZEN_N,
                "Unexpected frozen sample size")
    for state in zip(*sources):
        require(sum(c.n_cases for c in state) >= MIN_CELL
                and sum(c.n - c.n_cases for c in state) >= MIN_CELL,
                "A pooled state does not meet the event/non-event release floor")


def contact_cases(cells, cuts, quota):
    """Priority moves in the frozen low-to-high technology order."""
    target = quota * sum(c.weight for c in cells)
    remainder = target
    cases = F(0)
    edges = (0, *cuts, 5)
    for start, stop in zip(edges, edges[1:]):
        block = cells[start:stop]
        mass = sum(c.weight for c in block)
        if mass:
            contacted = min(mass, remainder)
            cases += contacted * sum(c.cases for c in block) / mass
            remainder -= contacted
    require(remainder == 0, "Expected quota was not filled")
    return target, cases


def choose_binary(fixed_scores, held_out):
    """Fit one cut across the four quotas using only remaining sources."""
    train = [score for i, score in enumerate(fixed_scores) if i != held_out]
    objectives = {
        name: sum(
            sum(s[name][k][1] for s in train) / sum(s[name][k][0] for s in train)
            for k in range(len(QUOTAS))
        ) / len(QUOTAS)
        for name in BINARY
    }
    return max(BINARY, key=objectives.__getitem__)  # On exact ties, earliest boundary wins.


def evaluate(sources, synthetic=False):
    validate(sources, synthetic)
    fixed_scores = [
        {name: [contact_cases(cells, cut, q) for q in QUOTAS] for name, cut in FIXED.items()}
        for cells in sources
    ]
    fits = [choose_binary(fixed_scores, i) for i in range(len(sources))]
    rows = []
    for method in (*FIXED, "train_selected_binary"):
        for k, quota in enumerate(QUOTAS):
            selected = [
                scores[fits[i] if method == "train_selected_binary" else method][k]
                for i, scores in enumerate(fixed_scores)
            ]
            deltas = [
                100 * (cases / contact - scores["digital"][k][1] / scores["digital"][k][0])
                for (contact, cases), scores in zip(selected, fixed_scores)
            ]
            rows.append({
                "quota": format(float(quota), ".2f"),
                "policy": method,
                "pooled_cases_per_100_expected_contacts": round(
                    float(100 * sum(e for _, e in selected) / sum(w for w, _ in selected)), 6
                ),
                "median_source_paired_delta_vs_digital": round(float(median(deltas)), 6),
            })
    return {
        "scope": "SYNTHETIC_TEST_ONLY" if synthetic else "RETROSPECTIVE_SOURCE_HOLDOUT",
        "source_count": len(sources),
        "outcome_scope": ("Generated test labels" if synthetic else
                          "Archived source-relative event evaluated within each held-out source"),
        "release_review_required": True,
        "results": rows,
    }


def synthetic_fixture():
    sources = []
    for j in range(SOURCE_COUNT):
        cells = []
        for i in range(5):
            n = 0 if (i, j) == (2, 0) else 120
            e = max(0, (44, 34, 27, 18, 9)[i] + j % 3 - 1) if n else 0
            cells.append(Cell(n, e, F(n), F(e)))
        sources.append(tuple(cells))
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    route = parser.add_mutually_exclusive_group(required=True)
    route.add_argument("--synthetic", action="store_true")
    route.add_argument("--input", type=Path)
    parser.add_argument("--confirm-authorized-aggregates", action="store_true")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    if args.synthetic:
        if args.confirm_authorized_aggregates or args.expected_sha256:
            parser.error("Authorisation and digest flags apply only to the input route")
        data = synthetic_fixture()
    else:
        if not args.confirm_authorized_aggregates:
            parser.error("The input route requires --confirm-authorized-aggregates")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256 or ""):
            parser.error("The input route requires a trusted --expected-sha256")
        try:
            with args.input.open("rb") as handle:
                payload = handle.read(65_537)
            require(len(payload) <= 65_536, "Aggregate input exceeds size limit")
            require(sha256(payload).hexdigest() == args.expected_sha256.lower(), "Input digest mismatch")
            data = parse_csv(payload)
        except (OSError, UnicodeError, csv.Error):
            parser.error("Could not read the declared aggregate CSV")
        except ValueError as exc:
            parser.error(str(exc))
    try:
        report = evaluate(data, synthetic=args.synthetic)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
