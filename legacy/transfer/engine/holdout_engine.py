#!/usr/bin/env python3
"""Exact-arithmetic, training-isolated source transfer evaluation for Paper E.

Input cells and source-level output remain private pending disclosure review.
The labels SYNTHETIC_TEST_ONLY and RETROSPECTIVE_TRANSFER are evidence scopes,
not statements that computational isolation recreates an unexposed experiment.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction as F
from hashlib import sha256
import io
import json
from pathlib import Path
import re
from typing import Mapping

FIELDS = ("source", "state", "n", "n_cases", "weight_mass", "case_mass")
QUOTAS = tuple(map(F, (".20", ".35", ".50", ".75")))
THREE_BLOCKS = ((1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4))
FIXED = {"five_states": (1, 2, 3, 4), "digital": (1,), "population_lottery": ()}
ALGORITHM = {
    "version": "H1-1.0",
    "quotas": ["0.20", "0.35", "0.50", "0.75"],
    "primary_quota": "0.50",
    "candidate_cuts": [list(c) for c in THREE_BLOCKS],
    "state_priority": [1, 2, 3, 4, 5],
    "marginal_block": "uniform contact probability",
    "selection": "minimise max_quota equal_source_mean(five_yield-candidate_yield)",
    "tie_break": "lexicographically smallest pair of cuts on exact equality",
    "yield_unit": "cases per 100 expected weighted contacts",
    "composition_unit": "percentage of expected weighted contacts",
    "crossvalidation": "retrospective source or country transfer",
    "uncertainty": "no sampling confidence intervals from aggregate cells",
}
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}")
INTEGER = re.compile(r"[0-9]{1,10}")
NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
HASH = re.compile(r"[0-9a-f]{64}")
WEIGHT_TOL = F("0.00000001")
EXPECTED_PROTOCOL_SHA256 = "80c5d6d9d69cbb38901ee1f169acc9d912ac11a3d1fb1604aa46037c6f3418bb"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(payload):
    return sha256(payload).hexdigest()


def code_hash():
    return digest(Path(__file__).read_bytes())


def algorithm_hash():
    return digest(canonical(ALGORITHM))


@dataclass(frozen=True)
class Cell:
    n: int
    n_cases: int
    weight: F
    cases: F


def validate(data: Mapping[str, tuple[Cell, ...]]):
    require(bool(data), "No aggregate sources")
    for source, cells in data.items():
        require(TOKEN.fullmatch(source) is not None, "Invalid source token")
        require(len(cells) == 5, "Each source requires five explicit states")
        for c in cells:
            require(type(c.n) is int and type(c.n_cases) is int, "Counts must be integers")
            require(0 <= c.n_cases <= c.n and 0 <= c.cases <= c.weight,
                    "Infeasible aggregate cell")
            require((c.n == 0) == (c.weight == 0), "Counts and weights disagree on empty support")
            require((c.n_cases == 0) == (c.cases == 0), "Counts and weights disagree on events")
            require((c.n_cases == c.n) == (c.cases == c.weight),
                    "Counts and weights disagree on full event support")
        n = sum(c.n for c in cells)
        require(n > 0, "Empty source")
        require(abs(sum(c.weight for c in cells) - n) <= WEIGHT_TOL * n,
                "Source weights are not normalised to its eligible count")


def parse_csv(payload):
    require(len(payload) <= 2_000_000, "Aggregate input exceeds size limit")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
    require(tuple(reader.fieldnames or ()) == FIELDS, "Unexpected CSV header")
    grouped = {}
    for row in reader:
        require(None not in row and all(isinstance(row[k], str) for k in FIELDS),
                "Invalid CSV row width")
        source, state, n, events, weight, cases = (row[k] for k in FIELDS)
        require(TOKEN.fullmatch(source) and state in "12345" and len(state) == 1,
                "Invalid source token or state")
        require(INTEGER.fullmatch(n) and INTEGER.fullmatch(events), "Invalid count")
        require(all(len(v) <= 64 and NUMBER.fullmatch(v) for v in (weight, cases)),
                "Invalid weighted mass")
        cells = grouped.setdefault(source, {})
        require(int(state) not in cells, "Duplicate source/state cell")
        cells[int(state)] = Cell(int(n), int(events), F(weight), F(cases))
    require(all(set(s) == {1, 2, 3, 4, 5} for s in grouped.values()),
            "Each source requires all five explicit states, including zero cells")
    data = {s: tuple(grouped[s][i] for i in range(1, 6)) for s in sorted(grouped)}
    validate(data)
    return data


def serialise_cells(data):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FIELDS)
    for source, cells in sorted(data.items()):
        for state, c in enumerate(cells, 1):
            with localcontext() as context:
                context.prec = 80
                masses = [format(Decimal(v.numerator)/Decimal(v.denominator), ".36f")
                          for v in (c.weight, c.cases)]
            writer.writerow((source, state, c.n, c.n_cases, *masses))
    return output.getvalue().encode()


def canonical_cells_hash(data):
    """Canonical fractions bind values independently of input row order/format."""
    rows = [[s, i, c.n, c.n_cases, str(c.weight), str(c.cases)]
            for s, cells in sorted(data.items()) for i, c in enumerate(cells, 1)]
    return digest(canonical(rows))


def evaluate_source(cells, cuts, quota):
    require(tuple(sorted(set(cuts))) == tuple(cuts)
            and all(c in (1, 2, 3, 4) for c in cuts), "Invalid ordered cuts")
    quota = F(quota)
    require(0 < quota <= 1, "Quota must be in (0, 1]")
    target = quota * sum(c.weight for c in cells)
    require(target > 0, "No eligible weighted mass")
    remainder = target
    state_contacts, state_events = [F(0)] * 5, [F(0)] * 5
    edges = (0, *cuts, 5)
    for start, stop in zip(edges, edges[1:]):
        mass = sum(c.weight for c in cells[start:stop])
        probability = min(F(1), remainder / mass) if mass else F(0)
        for i in range(start, stop):
            state_contacts[i] = probability * cells[i].weight
            state_events[i] = probability * cells[i].cases
        remainder -= probability * mass
    require(remainder == 0 and sum(state_contacts) == target, "Expected quota not filled")
    events = sum(state_events)
    event_total = sum(c.cases for c in cells)
    return {"contact_mass": target, "case_mass": events,
            "eligible_event_mass": event_total,
            "eligible_mass": sum(c.weight for c in cells),
            "yield": 100 * events / target,
            "recall_percent": 100 * events / event_total if event_total else None,
            "state_contacts": tuple(state_contacts),
            "state_shares_percent": tuple(100 * w / target for w in state_contacts)}


def training_selection(data):
    validate(data)
    objectives = {}
    for cuts in THREE_BLOCKS:
        per_quota = []
        for q in QUOTAS:
            gaps = [evaluate_source(c, FIXED["five_states"], q)["yield"]
                    - evaluate_source(c, cuts, q)["yield"] for c in data.values()]
            per_quota.append(sum(gaps) / len(gaps))
        objectives[cuts] = (max(per_quota), tuple(per_quota))
    chosen = min(THREE_BLOCKS, key=lambda c: (objectives[c][0], c))
    return chosen, objectives


def seal_lock(payload):
    return {**payload, "lock_sha256": digest(canonical(payload))}


def fit(data, countries, protocol_sha256, input_sha256=None, evidence_type="synthetic",
        provenance="Synthetic test fixture", prior_exposure="Synthetic fixture only"):
    require(evidence_type in ("synthetic", "empirical"), "Unknown evidence type")
    require(HASH.fullmatch(protocol_sha256) is not None, "Invalid protocol digest")
    require(set(countries) == set(data) and all(isinstance(c, str) and c.strip()
            for c in countries.values()), "Country metadata must match training sources")
    chosen, objectives = training_selection(data)
    payload = {
        "lock_version": "H1-1.0", "algorithm_sha256": algorithm_hash(),
        "code_sha256": code_hash(), "protocol_sha256": protocol_sha256,
        "training_input_sha256": input_sha256 or canonical_cells_hash(data),
        "training_cells_canonical_sha256": canonical_cells_hash(data),
        "training_sources": sorted(data), "training_countries": sorted(set(countries.values())),
        "source_countries": dict(sorted(countries.items())),
        "selected_cuts": list(chosen), "evidence_type": evidence_type,
        "provenance": provenance, "prior_exposure": prior_exposure,
        "objectives": [{"cuts": list(c), "max_mean_yield_loss_exact": str(v[0]),
                        "quota_mean_yield_loss_exact": [str(x) for x in v[1]]}
                       for c, v in objectives.items()],
        "chronology_note": "Local digest binds this file; it is not external preregistration.",
    }
    return seal_lock(payload)


def verify_lock(lock, protocol_sha256):
    payload = {k: v for k, v in lock.items() if k != "lock_sha256"}
    require(lock.get("lock_sha256") == digest(canonical(payload)), "Lock digest mismatch")
    require(lock.get("code_sha256") == code_hash(), "Engine code differs from fitted lock")
    require(lock.get("algorithm_sha256") == algorithm_hash(), "Algorithm differs from fitted lock")
    require(lock.get("protocol_sha256") == protocol_sha256, "Protocol differs from fitted lock")
    require(tuple(lock.get("selected_cuts", ())) in THREE_BLOCKS, "Invalid selected policy in lock")


def paired_row(source, country, policy, cuts, quota, value, five, digital):
    row = {"source": source, "country": country, "quota": format(float(quota), ".2f"), "policy": policy,
           "cuts": list(cuts), "expected_weighted_contacts": value["contact_mass"],
           "expected_weighted_cases": value["case_mass"],
           "eligible_weighted_event_mass": value["eligible_event_mass"],
           "eligible_weighted_mass": value["eligible_mass"],
           "realised_weighted_event_prevalence_percent": 100*value["eligible_event_mass"]/value["eligible_mass"],
           "cases_per_100_expected_contacts": value["yield"],
           "event_recall_percent": value["recall_percent"],
           "yield_delta_vs_five": value["yield"] - five["yield"],
           "yield_delta_vs_digital": value["yield"] - digital["yield"]}
    for i, share in enumerate(value["state_shares_percent"], 1):
        row[f"state_{i}_share_percent"] = share
        row[f"state_{i}_delta_vs_five_pp"] = share - five["state_shares_percent"][i-1]
        row[f"state_{i}_delta_vs_digital_pp"] = share - digital["state_shares_percent"][i-1]
    row["composition_tv_vs_five_pp"] = sum(abs(row[f"state_{i}_delta_vs_five_pp"])
                                               for i in range(1, 6)) / 2
    return row


def score(lock, data, countries, protocol_sha256, country_disjoint=False,
          evidence_type="synthetic", provenance="Synthetic test fixture",
          prior_exposure="Synthetic fixture only"):
    verify_lock(lock, protocol_sha256)
    validate(data)
    require(set(countries) == set(data), "Country metadata must match test sources")
    require(not set(data) & set(lock["training_sources"]), "Training and test sources overlap")
    if country_disjoint:
        require(not set(countries.values()) & set(lock["training_countries"]),
                "Training and test countries overlap")
    require(evidence_type == lock["evidence_type"], "Training and test evidence scopes differ")
    policies = {**FIXED, "train_selected_three_block": tuple(lock["selected_cuts"])}
    rows = []
    for source, cells in sorted(data.items()):
        for quota in QUOTAS:
            scores = {p: evaluate_source(cells, cuts, quota) for p, cuts in policies.items()}
            for policy, cuts in policies.items():
                rows.append(paired_row(source, countries[source], policy, cuts, quota,
                                       scores[policy], scores["five_states"], scores["digital"]))
    return {"scope": "SYNTHETIC_TEST_ONLY" if evidence_type == "synthetic" else "RETROSPECTIVE_TRANSFER",
            "lock_sha256": lock["lock_sha256"], "test_sources": sorted(data),
            "test_cells_canonical_sha256": canonical_cells_hash(data),
            "test_provenance": provenance, "test_prior_exposure": prior_exposure,
            "country_disjoint_enforced": country_disjoint,
            "release_review_required": True, "results": rows}


def summary_rows(rows, unit):
    """Primary equal transfer units; secondary totals at common expected quotas."""
    output = []
    groups = sorted({(r["quota"], r["policy"]) for r in rows}, key=lambda k: (F(k[0]), k[1]))
    numeric = [k for k in rows[0] if k not in ("source", "country", "quota", "policy", "cuts")]
    for quota, policy in groups:
        subset = [r for r in rows if (r["quota"], r["policy"]) == (quota, policy)]
        units = {}
        for row in subset:
            units.setdefault(row["country" if unit == "country" else "source"], []).append(row)
        primary = {"quota": quota, "policy": policy,
                   "aggregation": "equal_country_within_country_equal_source" if unit == "country"
                   else "equal_source", "unit_count": len(units), "source_count": len(subset)}
        for key in numeric:
            means = [sum(r[key] for r in group) / len(group) for group in units.values()
                     if all(r[key] is not None for r in group)]
            primary[key] = sum(means) / len(means) if len(means) == len(units) else None
        primary["mass_note"] = "Contact and case masses here are mean per transfer unit, not totals."
        output.append(primary)
        total_contacts = sum(r["expected_weighted_contacts"] for r in subset)
        pooled = {"quota": quota, "policy": policy, "aggregation": "expected_contact_weight_pooled",
                  "unit_count": len(units), "source_count": len(subset),
                  "expected_weighted_contacts": total_contacts,
                  "expected_weighted_cases": sum(r["expected_weighted_cases"] for r in subset),
                  "eligible_weighted_event_mass": sum(r["eligible_weighted_event_mass"] for r in subset),
                  "eligible_weighted_mass": sum(r["eligible_weighted_mass"] for r in subset)}
        for key in numeric:
            if key in ("expected_weighted_contacts", "expected_weighted_cases", "eligible_weighted_event_mass", "eligible_weighted_mass"):
                continue
            # Recall has a different denominator; never average it with contact weights.
            if key == "event_recall_percent":
                total_events = pooled["eligible_weighted_event_mass"]
                pooled[key] = 100*pooled["expected_weighted_cases"]/total_events if total_events else None
            else:
                pooled[key] = sum(r[key]*r["expected_weighted_contacts"] for r in subset)/total_contacts
        pooled["composition_tv_vs_five_pp"] = sum(abs(pooled[f"state_{i}_delta_vs_five_pp"])
                                                    for i in range(1, 6))/2
        pooled["mass_note"] = "Contact and case masses here are totals over tested sources."
        output.append(pooled)
    return output


def crossvalidate(data, countries, protocol_sha256, unit="source", evidence_type="synthetic",
                  provenance="Synthetic test fixture", prior_exposure="Synthetic fixture only"):
    require(unit in ("source", "country"), "Unknown transfer unit")
    validate(data)
    require(set(countries) == set(data), "Country metadata must match all sources")
    groups = {s: (s,) for s in sorted(data)} if unit == "source" else {
        country: tuple(s for s in sorted(data) if countries[s] == country)
        for country in sorted(set(countries.values()))}
    require(len(groups) >= 2, "At least two transfer units required")
    folds, rows = [], []
    for group, heldout in groups.items():
        training = {s: c for s, c in data.items() if s not in heldout}
        testing = {s: data[s] for s in heldout}
        lock = fit(training, {s: countries[s] for s in training}, protocol_sha256,
                   evidence_type=evidence_type, provenance=provenance, prior_exposure=prior_exposure)
        report = score(lock, testing, {s: countries[s] for s in testing}, protocol_sha256,
                       country_disjoint=unit == "country", evidence_type=evidence_type,
                       provenance=provenance, prior_exposure=prior_exposure)
        folds.append({"held_out_unit": group, "held_out_sources": list(heldout),
                      "lock": lock, "score_scope": report["scope"]})
        rows.extend(report["results"])
    return {"scope": "SYNTHETIC_TEST_ONLY" if evidence_type == "synthetic" else "RETROSPECTIVE_TRANSFER",
            "unit": unit, "source_count": len(data), "country_count": len(set(countries.values())),
            "input_cells_canonical_sha256": canonical_cells_hash(data),
            "algorithm": ALGORITHM, "protocol_sha256": protocol_sha256,
            "release_review_required": True, "folds": folds, "results": rows,
            "summary": summary_rows(rows, unit),
            "limitations": ["Retrospective transfer after historical pooled exposure.",
                            "Local freezing does not establish independent prospective validation.",
                            "No sampling confidence intervals or welfare interpretation."]}


def jsonable(value):
    if isinstance(value, F):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(jsonable(obj), handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def load_input(path, manifest_path):
    payload = path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("input_sha256") == digest(payload), "Input digest differs from manifest")
    require(manifest.get("evidence_type") in ("synthetic", "empirical"),
            "Manifest requires explicit synthetic or empirical evidence_type")
    for name in ("provenance", "prior_exposure"):
        require(isinstance(manifest.get(name), str) and manifest[name].strip(),
                "Manifest requires provenance and prior exposure statements")
    data = parse_csv(payload)
    countries = manifest.get("sources")
    require(isinstance(countries, dict) and set(countries) == set(data)
            and all(isinstance(c, str) and c.strip() for c in countries.values()),
            "Manifest sources must map every source to its reporting country")
    return data, countries, manifest


def checked_protocol(path):
    payload = path.read_bytes()
    actual = digest(payload)
    require(actual == EXPECTED_PROTOCOL_SHA256, "Protocol is not the frozen H1 protocol")
    protocol = json.loads(payload.decode("utf-8"))
    require(protocol.get("protocol_id") == "PAPERE_H1_TRANSFER_20261105_v1",
            "Unexpected protocol identity")
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("fit", "score", "crossvalidate"):
        sub = commands.add_parser(command)
        sub.add_argument("--input", type=Path, required=True)
        sub.add_argument("--manifest", type=Path, required=True)
        sub.add_argument("--protocol", type=Path, required=True)
        sub.add_argument("--output", type=Path, required=True)
        if command == "score":
            sub.add_argument("--lock", type=Path, required=True)
            sub.add_argument("--country-disjoint", action="store_true")
        if command == "crossvalidate":
            sub.add_argument("--unit", choices=("source", "country"), default="source")
    args = parser.parse_args(argv)
    try:
        data, countries, manifest = load_input(args.input, args.manifest)
        protocol_sha256 = checked_protocol(args.protocol)
        common = {"evidence_type": manifest["evidence_type"],
                  "provenance": manifest["provenance"], "prior_exposure": manifest["prior_exposure"]}
        if args.command == "fit":
            result = fit(data, countries, protocol_sha256, digest(args.input.read_bytes()), **common)
        elif args.command == "score":
            lock = json.loads(args.lock.read_text(encoding="utf-8"))
            result = score(lock, data, countries, protocol_sha256,
                           country_disjoint=args.country_disjoint, **common)
            result["test_input_sha256"] = manifest["input_sha256"]
        else:
            result = crossvalidate(data, countries, protocol_sha256, args.unit, **common)
            result["input_sha256"] = manifest["input_sha256"]
        require(not args.output.exists(), "Output already exists; choose a new execution path")
        write_json(args.output, result)
        print(json.dumps({"status": "PASS", "command": args.command,
                          "evidence_type": manifest["evidence_type"], "output": str(args.output)}))
    except (ValueError, OSError, UnicodeError, csv.Error, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
