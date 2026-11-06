#!/usr/bin/env python3
"""Independent row-level computation. No canonical computational modules imported.

No row data, establishment IDs or row predictions are written. All saved outputs
are private aggregate verification results, not evidence from a new sample.
"""
import argparse
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import platform
import zipfile

import numpy as np
import pandas as pd

RAW_SHA = "6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e"
MEMBER_SHA = "f61a2c6e09f4763818ae1d4db8b330e97bffd8bb0824c2d833b79d728152bd17"
PROTOCOL_SHA = "80c5d6d9d69cbb38901ee1f169acc9d912ac11a3d1fb1604aa46037c6f3418bb"
P_FP = "59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76"
B_FP = "49f35215e472132af24dcb2f80388ca2e23edb81613aaa11df8b7d9f7ad6f1c2"
STATES = ["ib9b" + str(i) for i in range(1, 6)]
QUOTAS = (.20, .35, .50, .75)
CANDIDATES = tuple(itertools.combinations((1, 2, 3, 4), 2))
FIXED = {"five_states": (1, 2, 3, 4), "digital": (1,), "population_lottery": ()}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def country(source):
    return {"India_Wave2_New": "India", "BurkinaFaso": "Burkina Faso",
            "Korea": "Republic of Korea", "Vietnam": "Viet Nam"}.get(source, source)


def fingerprint(d):
    ordered = d.sort_values(["country", "firmid"], kind="mergesort")
    lines = "\n".join(str(s) + "|" + str(int(i)) for s, i in
                      ordered[["country", "firmid"]].itertuples(index=False, name=None)) + "\n"
    return sha(lines.encode())


def reference(raw_path, protocol_path):
    payload = raw_path.read_bytes()
    assert sha(payload) == RAW_SHA
    protocol_bytes = protocol_path.read_bytes()
    assert sha(protocol_bytes) == PROTOCOL_SHA
    protocol = json.loads(protocol_bytes)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert z.testzip() is None
        member = z.read("fat0_raw_data_qje.csv")
    assert sha(member) == MEMBER_SHA
    fields = ["country", "firmid", "base_wt", "e6a", "s7", *STATES]
    d = pd.read_csv(io.BytesIO(member), usecols=fields, low_memory=False)
    assert len(d) == 21055 and not d.firmid.duplicated().any()
    flags = d[STATES]
    eligible = ((d.base_wt > 0) & (d.e6a > 0) & (d.s7 > 0) &
                flags.isin([0, 1]).all(axis=1) & flags.sum(axis=1).eq(1))
    primary = d.loc[eligible & d.country.isin(protocol["primary_sources"])].copy()
    broad = d.loc[eligible & d.country.isin(protocol["primary_sources"] + protocol["excluded_primary_targets"])].copy()
    assert len(primary) == 14412 and fingerprint(primary) == P_FP
    assert len(broad) == 14818 and fingerprint(broad) == B_FP
    sources, cells, quantile_checks = {}, [], []
    for source, g in broad.groupby("country", sort=True):
        g = g.sort_values("firmid", kind="mergesort")
        raw_weights = g.base_wt.to_numpy(dtype=float)
        weights = raw_weights / (math.fsum(raw_weights) / len(g))
        outcome = np.log(g.e6a.to_numpy(dtype=float) / g.s7.to_numpy(dtype=float))
        order = np.argsort(outcome, kind="stable")
        cumulative = np.cumsum(weights[order])
        threshold_pos = np.flatnonzero(cumulative >= cumulative[-1] * .2)[0]
        threshold = outcome[order[threshold_pos]]
        event = outcome <= threshold
        # The comparison is diagnostic only; it never substitutes another label.
        raw_cumulative = np.cumsum(raw_weights[order])
        raw_pos = np.flatnonzero(raw_cumulative >= raw_cumulative[-1] * .2)[0]
        raw_event = outcome <= outcome[order[raw_pos]]
        state = np.argmax(g[STATES].to_numpy(), axis=1) + 1
        data = {"weight": weights, "event": event, "state": state, "n": len(g)}
        sources[source] = data
        for s in range(1, 6):
            m = state == s
            cells.append({"source": source, "state": s, "n": int(m.sum()),
                          "n_cases": int((m & event).sum()),
                          "weight_mass": math.fsum(weights[m]),
                          "case_mass": math.fsum(weights[m & event])})
        quantile_checks.append({"source": source, "n": len(g),
                                "scale_membership_difference_n": int((raw_event != event).sum()),
                                "weighted_event_prevalence_percent": 100 * math.fsum(weights[event]) / math.fsum(weights)})
    return protocol, sources, cells, quantile_checks


def score(data, cuts, quota):
    """Allocate uniform contact probabilities to actual rows in each block."""
    w, e, s = data["weight"], data["event"], data["state"]
    block = np.searchsorted(cuts, s, side="left")
    prob = np.zeros(len(w), dtype=float)
    target = quota * math.fsum(w)
    remaining = target
    for k in range(len(cuts) + 1):
        mask = block == k
        mass = math.fsum(w[mask])
        chance = min(1., max(0., remaining / mass)) if mass else 0.
        prob[mask] = chance
        remaining -= chance * mass
    contacts = math.fsum(w * prob)
    cases = math.fsum(w * prob * e)
    event_mass = math.fsum(w[e])
    assert abs(contacts - target) < 1e-8
    shares = [100 * math.fsum((w * prob)[s == k]) / contacts for k in range(1, 6)]
    return {"expected_weighted_contacts": contacts, "expected_weighted_cases": cases,
            "eligible_weighted_mass": math.fsum(w), "eligible_weighted_event_mass": event_mass,
            "cases_per_100_expected_contacts": 100 * cases / contacts,
            "event_recall_percent": 100 * cases / event_mass if event_mass else None,
            "realised_weighted_event_prevalence_percent": 100 * event_mass / math.fsum(w),
            **{f"state_{i}_share_percent": value for i, value in enumerate(shares, 1)}}


def select(sources):
    objectives = {}
    for cuts in CANDIDATES:
        per_q = []
        for q in QUOTAS:
            losses = [score(d, (1, 2, 3, 4), q)["cases_per_100_expected_contacts"] -
                      score(d, cuts, q)["cases_per_100_expected_contacts"] for d in sources.values()]
            per_q.append(math.fsum(losses) / len(losses))
        objectives[cuts] = (max(per_q), per_q)
    minimum = min(v[0] for v in objectives.values())
    # Only numerical equality within 1e-11 is collapsed in this independent
    # floating evaluator. Canonical exact-rational objectives are compared below.
    winners = [c for c, v in objectives.items() if abs(v[0] - minimum) <= 1e-11]
    return min(winners), objectives


def compare(raw_path, protocol_path, run_dir):
    protocol, sources, cells, quantile_checks = reference(raw_path, protocol_path)
    maxima = Counter()
    counts = Counter()

    def close(label, actual, expected, tolerance=1e-9):
        if actual is None or expected is None:
            assert actual is None and expected is None, label
            return
        error = abs(float(actual) - float(expected))
        maxima[label] = max(maxima[label], error)
        counts[label] += 1
        assert error <= tolerance, (label, error)

    supplied_cells = {}
    for role in ("primary", "excluded_primary"):
        with (run_dir / "private_source_cells" / (role + "_cells.csv")).open() as f:
            for r in csv.DictReader(f):
                supplied_cells[r["source"], int(r["state"])] = r
    for r in cells:
        canonical = supplied_cells[r["source"], r["state"]]
        for name in ("n", "n_cases"):
            assert r[name] == int(canonical[name]), (r["source"], r["state"], name)
            counts["exact_cell_count"] += 1
        for name in ("weight_mass", "case_mass"):
            close("cell_" + name, r[name], canonical[name], 1e-9)

    primary = {s: d for s, d in sources.items() if s in protocol["primary_sources"]}
    all_lock = json.loads((run_dir / "ALL_PRIMARY_TRAINING_LOCK.json").read_text())

    def canonical_bytes(data):
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    def cell_digest(source_set):
        records = []
        for source in sorted(source_set):
            for state in range(1, 6):
                r = supplied_cells[source, state]
                records.append([source, state, int(r["n"]), int(r["n_cases"]),
                                str(Fraction(r["weight_mass"])), str(Fraction(r["case_mass"]))])
        return sha(canonical_bytes(records))

    code_sha = sha((protocol_path.parent.parent / "engine/holdout_engine.py").read_bytes())
    source_report = json.loads((run_dir / "SOURCE_TRANSFER.json").read_text())
    algorithm_sha = sha(canonical_bytes(source_report["algorithm"]))

    def verify_lock(lock, training_set, explicit_input=False):
        assert lock["lock_sha256"] == sha(canonical_bytes({k: v for k, v in lock.items() if k != "lock_sha256"}))
        assert lock["code_sha256"] == code_sha
        assert lock["protocol_sha256"] == PROTOCOL_SHA
        assert lock["algorithm_sha256"] == algorithm_sha
        assert set(lock["training_sources"]) == set(training_set)
        assert lock["training_cells_canonical_sha256"] == cell_digest(training_set)
        expected_input = sha((run_dir / "private_source_cells/primary_cells.csv").read_bytes()) if explicit_input else cell_digest(training_set)
        assert lock["training_input_sha256"] == expected_input
        counts["lock_digest_and_training_identity"] += 1

    verify_lock(all_lock, primary, explicit_input=True)
    chosen, objectives = select(primary)
    assert list(chosen) == all_lock["selected_cuts"]
    counts["selection_all_primary"] += 1
    for item in all_lock["objectives"]:
        cut = tuple(item["cuts"])
        close("training_objective", objectives[cut][0], float(Fraction(item["max_mean_yield_loss_exact"])))
        for actual, value in zip(objectives[cut][1], item["quota_mean_yield_loss_exact"]):
            close("training_objective_quota", actual, float(Fraction(value)))

    canonical_rows, fold_choices = [], []
    excluded_report = json.loads((run_dir / "EXCLUDED_PRIMARY_TRANSFER.json").read_text())
    assert excluded_report["lock_sha256"] == all_lock["lock_sha256"]
    assert excluded_report["test_cells_canonical_sha256"] == cell_digest(protocol["excluded_primary_targets"])
    canonical_rows += excluded_report["results"]
    for fname, unit in (("SOURCE_TRANSFER.json", "source"), ("COUNTRY_TRANSFER.json", "country")):
        report = json.loads((run_dir / fname).read_text())
        canonical_rows += report["results"]
        for fold in report["folds"]:
            heldout = set(fold["held_out_sources"])
            train = {s: d for s, d in primary.items() if s not in heldout}
            verify_lock(fold["lock"], train)
            fit, vals = select(train)
            assert list(fit) == fold["lock"]["selected_cuts"], (unit, sorted(heldout), fit, fold["lock"]["selected_cuts"])
            assert not heldout.intersection(fold["lock"]["training_sources"])
            if unit == "country":
                test_countries = {country(s) for s in heldout}
                assert not test_countries.intersection(country(s) for s in train)
                if "India" in test_countries:
                    assert heldout == {"India", "India_Wave2_New"}
            for item in fold["lock"]["objectives"]:
                close("fold_training_objective", vals[tuple(item["cuts"])][0],
                      float(Fraction(item["max_mean_yield_loss_exact"])))
            counts["training_fold_selection"] += 1
            fold_choices.append({"unit": unit, "heldout": sorted(heldout), "selected_cuts": list(fit)})

    for r in canonical_rows:
        d = sources[r["source"]]
        q = float(Fraction(r["quota"]))
        value = score(d, tuple(r["cuts"]), q)
        five, digital = score(d, FIXED["five_states"], q), score(d, FIXED["digital"], q)
        for key, expected in value.items():
            close("scored_" + key, expected, r[key])
        close("yield_delta_vs_five", value["cases_per_100_expected_contacts"] - five["cases_per_100_expected_contacts"], r["yield_delta_vs_five"])
        close("yield_delta_vs_digital", value["cases_per_100_expected_contacts"] - digital["cases_per_100_expected_contacts"], r["yield_delta_vs_digital"])
        tv = 0.
        for i in range(1, 6):
            key = f"state_{i}_share_percent"
            delta = value[key] - five[key]
            close("composition_delta_vs_five", delta, r[f"state_{i}_delta_vs_five_pp"])
            close("composition_delta_vs_digital", value[key] - digital[key], r[f"state_{i}_delta_vs_digital_pp"])
            tv += abs(delta) / 2
        close("composition_tv", tv, r["composition_tv_vs_five_pp"])
        counts["source_policy_quota_rows"] += 1

    # Independent aggregation check, including recall's event denominator and TV
    # of a pooled contact list rather than the mean of source-level distances.
    for fname, unit in (("SOURCE_TRANSFER.json", "source"), ("COUNTRY_TRANSFER.json", "country")):
        report = json.loads((run_dir / fname).read_text())
        for summary in report["summary"]:
            rows = [r for r in report["results"] if r["quota"] == summary["quota"] and r["policy"] == summary["policy"]]
            if summary["aggregation"] == "expected_contact_weight_pooled":
                total_c = math.fsum(r["expected_weighted_contacts"] for r in rows)
                total_e = math.fsum(r["expected_weighted_cases"] for r in rows)
                total_event = math.fsum(r["eligible_weighted_event_mass"] for r in rows)
                close("summary_pooled_yield", 100 * total_e / total_c, summary["cases_per_100_expected_contacts"])
                close("summary_pooled_recall", 100 * total_e / total_event, summary["event_recall_percent"])
                shares = [math.fsum(r[f"state_{i}_share_percent"] * r["expected_weighted_contacts"] for r in rows) / total_c for i in range(1, 6)]
            else:
                group_key = "country" if unit == "country" else "source"
                groups = {}
                for r in rows:
                    groups.setdefault(r[group_key], []).append(r)
                for key in ("cases_per_100_expected_contacts", "yield_delta_vs_five", "yield_delta_vs_digital", "composition_tv_vs_five_pp"):
                    value = math.fsum(math.fsum(r[key] for r in g) / len(g) for g in groups.values()) / len(groups)
                    close("summary_equal_unit", value, summary[key])
                shares = [math.fsum(math.fsum(r[f"state_{i}_share_percent"] for r in g)/len(g) for g in groups.values())/len(groups) for i in range(1, 6)]
            for i, share in enumerate(shares, 1):
                close("summary_composition", share, summary[f"state_{i}_share_percent"])
            counts["summary_rows"] += 1

    return {"status": "PASS", "scope": "INDEPENDENT_EMPIRICAL_RECOMPUTATION_FROM_SAME_PINNED_RAW_SAMPLE",
            "independent_new_sample": False, "imports_canonical_computational_modules": False,
            "raw_sha256": RAW_SHA, "protocol_sha256": PROTOCOL_SHA,
            "primary_n": 14412, "broad_n": 14818, "targets_n": 406,
            "count_checks": dict(counts), "maximum_absolute_errors": dict(maxima),
            "absolute_tolerance": 1e-9, "selector_float_tie_tolerance": 1e-11,
            "all_primary_selected_cuts": list(chosen), "fold_choices": fold_choices,
            "source_quantile_diagnostics": quantile_checks,
            "row_level_outputs_written": False,
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
            "verifier_sha256": sha(Path(__file__).read_bytes())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microdata", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--canonical-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = compare(args.microdata, args.protocol, args.canonical_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "checks": receipt["count_checks"],
                      "max_error": max(receipt["maximum_absolute_errors"].values()),
                      "all_primary_selected_cuts": receipt["all_primary_selected_cuts"]}))
