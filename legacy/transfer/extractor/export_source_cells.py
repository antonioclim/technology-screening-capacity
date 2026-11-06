#!/usr/bin/env python3
"""Private aggregate export from the exact archived FAT input, with frozen parity checks."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd
import scipy

ROOT = Path(__file__).resolve().parent
PROTOCOL_SHA = "f3d6536f0de1ccd09cb18f3e73a4a7071eeada16a3423cbfca0572285ae6fa72"
EXECUTOR_SHA = "0ac2f1d60dbafcdc5edd763e682759732f326cceb66639cdf50647d34987a402"
E3_SHA = "f63fa3abf1adf0da613ed70cbcbd2fb56ea40710b0519fc29449ccb3611a0422"
E2_SHA = "7a2ac874b1bd12fcebf102b602f81ff6d7471595f46dd68f2230ed9ed5073cb7"
PRIMARY_FINGERPRINT = "59d49ff980b98de612b32d721ed35dc80a92fb3175be2e1ddfcf8d36168c6f76"
BROAD_FINGERPRINT = "49f35215e472132af24dcb2f80388ca2e23edb81613aaa11df8b7d9f7ad6f1c2"
REFERENCE_HASHES = {
    "X04_LOW_PERFORMANCE_THRESHOLD_GRID.csv": "7069e707e0b380e19c2a71c5d70c486a0612763c349dda9e45d9502aebb0e21d",
    "X06_TRANSITION_GROUP_DECOMPOSITION.csv": "b523df3653b407acbe6e56772b01605c5232530f484b776ac41fb631f232c83e",
    "X07_ALL_MONOTONE_CUTPOINT_CLASSIFICATION.csv": "4fb38483aacf0d8b327634b8fc88c1dc18555c3e1e656e1d51c5bb442053af7d",
}
FIELDS = ("source", "state", "n", "n_cases", "weight_mass", "case_mass")
EXCLUDED_PRIMARY = ("BurkinaFaso", "Cambodia")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned(path, expected):
    require(Path(path).is_file(), "Pinned input is absent")
    require(digest(path) == expected, "Pinned input SHA-256 mismatch")


def load_frozen_executor(baseline):
    path = Path(baseline) / "upstream/run_e4_frozen_analysis_v1.0.2.py"
    pinned(path, EXECUTOR_SHA)
    pinned(Path(baseline) / "protocols/E2_OUTCOME_AND_SAMPLE_CONTRACT.json", E2_SHA)
    protocol_path = Path(baseline) / "protocols/E3_PREANALYSIS_PROTOCOL.json"
    pinned(protocol_path, E3_SHA)
    spec = importlib.util.spec_from_file_location("papere_e4_frozen_export_vendor", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.load_protocol(protocol_path, E3_SHA)
    return module


def add_event(frame, frozen):
    """Apply archived source-local weights and inclusive weighted quantile labels."""
    out = frozen.add_outcomes_and_weights(frame)
    out["H1_EVENT"] = False
    for _, group in out.groupby("country", sort=True):
        threshold = frozen.weighted_quantile_threshold(
            group["Y_PRIMARY_RAW"].to_numpy(),
            group["W_PRIMARY_SOURCE_MEAN1"].to_numpy(), .20)
        out.loc[group.index, "H1_EVENT"] = group["Y_PRIMARY_RAW"].le(threshold)
    require(np.isfinite(out["Y_PRIMARY_RAW"]).all(), "Non-finite eligible outcome")
    require(np.isfinite(out["W_PRIMARY_SOURCE_MEAN1"]).all(), "Non-finite eligible weight")
    return out


def aggregate(frame):
    rows = []
    for source, group in frame.groupby("country", sort=True):
        weights = group["W_PRIMARY_SOURCE_MEAN1"]
        require(abs(math.fsum(weights) - len(group)) <= 1e-8 * len(group),
                "Source weights are not mean one")
        for state in range(1, 6):
            cell = group.loc[group["most_state"].eq(state)]
            cases = cell.loc[cell["H1_EVENT"]]
            rows.append({"source": str(source), "state": state, "n": len(cell),
                         "n_cases": len(cases),
                         "weight_mass": format(math.fsum(cell["W_PRIMARY_SOURCE_MEAN1"]), ".18f"),
                         "case_mass": format(math.fsum(cases["W_PRIMARY_SOURCE_MEAN1"]), ".18f")})
    return rows


def quantile_scale_diagnostics(frame, frozen):
    """Compare two weight scales without changing any frozen event label."""
    diagnostics = []
    for source, group in frame.groupby("country", sort=True):
        values = group["Y_PRIMARY_RAW"].to_numpy()
        normalised = group["W_PRIMARY_SOURCE_MEAN1"].to_numpy()
        raw = group["base_wt"].astype(float).to_numpy()
        frozen_threshold = frozen.weighted_quantile_threshold(values, normalised, .20)
        raw_scale_threshold = frozen.weighted_quantile_threshold(values, raw, .20)
        frozen_labels, raw_scale_labels = values <= frozen_threshold, values <= raw_scale_threshold
        require(np.array_equal(frozen_labels, group["H1_EVENT"].to_numpy()),
                "Stored event labels disagree with the frozen threshold")
        mismatch = frozen_labels != raw_scale_labels
        diagnostics.append({
            "source": str(source), "eligible_n": len(group),
            "frozen_normalised_weight_threshold": frozen_threshold,
            "raw_weight_scale_threshold": raw_scale_threshold,
            "event_membership_difference_n": int(mismatch.sum()),
            "event_membership_difference_normalised_weight_mass": float(math.fsum(normalised[mismatch])),
            "frozen_event_weighted_share": float(math.fsum(normalised[frozen_labels]) / math.fsum(normalised)),
            "finite_precision_scale_difference_flag": bool(mismatch.any()),
            "frozen_labels_preserved": True,
            "interpretation": "Audit diagnostic only: positive rescaling is mathematically invariant but the archived floating-point cumulative threshold can differ at a numerical boundary. No replacement labels or alternative screening results are emitted."
        })
    return diagnostics


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def load_references(directory):
    result = {}
    for name, expected in REFERENCE_HASHES.items():
        path = Path(directory) / name
        pinned(path, expected)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            result[name[:3]] = list(csv.DictReader(handle))
    return result


def close(actual, expected, label, checks, atol=1e-8):
    error = abs(float(actual) - float(expected))
    require(error <= atol * max(1.0, abs(float(expected))), "Frozen aggregate parity failed: " + label)
    checks.append({"check": label, "absolute_error": error, "passed": True})


def check_parity(rows, references):
    checks = []
    n = sum(int(r["n"]) for r in rows)
    total = math.fsum(float(r["weight_mass"]) for r in rows)
    cases = math.fsum(float(r["case_mass"]) for r in rows)
    require(n == 14412, "Primary sample count mismatch")
    close(total, 14412, "total normalised weight", checks)
    for state in range(1, 6):
        cell = [r for r in rows if int(r["state"]) == state]
        ref = next(r for r in references["X06"] if r["group_id"] == f"state_{state}")
        require(sum(int(r["n"]) for r in cell) == int(ref["unweighted_n"]),
                "Frozen aggregate parity failed: state count")
        weight = math.fsum(float(r["weight_mass"]) for r in cell)
        event = math.fsum(float(r["case_mass"]) for r in cell)
        close(weight, ref["weighted_total"], f"state {state} weight", checks)
        close(event / weight, ref["weighted_low_performance_share"], f"state {state} event share", checks)
    for series in ("X04", "X07"):
        for ref in references[series]:
            if float(ref["low_performance_quantile"]) != .2:
                continue
            cut = int(ref["cut_state"])
            selected = [r for r in rows if int(r["state"]) < cut]
            wsel = math.fsum(float(r["weight_mass"]) for r in selected)
            esel = math.fsum(float(r["case_mass"]) for r in selected)
            close(cases / total, ref["low_performance_share"], series + " prevalence", checks)
            close(wsel / total, ref["target_share"], series + f" cut {cut} share", checks)
            close(esel / cases, ref["recall"], series + f" cut {cut} recall", checks)
            close(esel / wsel, ref["positive_predictive_value"], series + f" cut {cut} yield", checks)
    return checks


def coverage_diagnostics(raw, broad):
    diagnostics = []
    for source, group in raw.groupby("country", sort=True):
        eligible = broad.loc[broad["country"].eq(source)]
        diagnostics.append({"source": str(source), "raw_n": len(group),
                            "positive_sales_n": int(group["e6a"].gt(0).sum()),
                            "positive_sales_fraction": float(group["e6a"].gt(0).mean()),
                            "broad_eligible_n": len(eligible),
                            "eligible_fraction_of_source": len(eligible) / len(group)})
    return diagnostics


def write_sync(path, payload):
    with Path(path).open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def export(microdata, baseline, protocol, output, reference):
    output = Path(output).resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            "Output must be a new or empty directory")
    pinned(protocol, PROTOCOL_SHA)
    frozen = load_frozen_executor(baseline)
    references = load_references(reference)
    raw = frozen.load_real_microdata(Path(microdata))
    prepared = frozen.prepare_full_frame(raw)
    primary = frozen.build_sample(prepared, "PRIMARY_S60_N200")
    broad = frozen.build_sample(prepared, "BROAD_AVAILABLE_N20")
    require(len(primary) == 14412 and frozen.sample_fingerprint(primary) == PRIMARY_FINGERPRINT,
            "Primary sample identity mismatch")
    require(len(broad) == 14818 and frozen.sample_fingerprint(broad) == BROAD_FINGERPRINT,
            "Broad sample identity mismatch")
    require(set(primary["country"]) == set(frozen.PRIMARY_SOURCES), "Primary source identity mismatch")
    target = broad.loc[broad["country"].isin(EXCLUDED_PRIMARY)].copy()
    require(len(target) == 406 and set(target["country"]) == set(EXCLUDED_PRIMARY),
            "Excluded-primary target identity mismatch")
    primary = add_event(primary, frozen)
    target = add_event(target, frozen)
    primary_rows, target_rows = aggregate(primary), aggregate(target)
    checks = check_parity(primary_rows, references)
    quantile_diagnostics = {
        "primary": quantile_scale_diagnostics(primary, frozen),
        "excluded_primary": quantile_scale_diagnostics(target, frozen)
    }
    # Never emit a success marker or partial aggregate payload before all gates pass.
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".h1-export-", dir=output.parent))
    try:
        for role, rows in (("primary", primary_rows), ("excluded_primary", target_rows)):
            payload = csv_bytes(rows)
            write_sync(staged / f"{role}_cells.csv", payload)
            sources = {s: frozen.reporting_country(s) for s in sorted({r["source"] for r in rows})}
            manifest = {"evidence_type": "empirical", "input_sha256": hashlib.sha256(payload).hexdigest(),
                        "sources": sources,
                        "provenance": "Private source-state aggregates from exact pinned archived FAT input; frozen sample/outcome functions; local output not cleared for public redistribution.",
                        "prior_exposure": "Primary pooled results and broad-sample sensitivity were previously inspected. This is retrospective transfer, not prospective external validation.",
                        "role": role, "protocol_sha256": PROTOCOL_SHA,
                        "raw_container_sha256": frozen.EXPECTED_CONTAINER_SHA256,
                        "raw_member_sha256": frozen.EXPECTED_MEMBER_SHA256}
            write_sync(staged / f"{role}_manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        receipt = {"status": "EMPIRICAL_AGGREGATE_EXPORT_PASSED", "raw_rows": len(raw),
                   "raw_columns_expected": 723, "primary_n": len(primary), "target_n": len(target),
                   "protocol_sha256": PROTOCOL_SHA, "executor_sha256": EXECUTOR_SHA,
                   "exporter_sha256": digest(__file__), "primary_membership_sha256": PRIMARY_FINGERPRINT,
                   "broad_membership_sha256": BROAD_FINGERPRINT,
                   "parity_checks": checks, "coverage_diagnostics": coverage_diagnostics(raw, broad),
                   "quantile_scale_diagnostics": quantile_diagnostics,
                   "quantile_scale_difference_found": any(
                       r["finite_precision_scale_difference_flag"]
                       for group in quantile_diagnostics.values() for r in group),
                   "row_level_outputs_written": False, "public_release_approved": False,
                   "environment": {"python": platform.python_version(), "numpy": np.__version__,
                                   "pandas": pd.__version__, "scipy": scipy.__version__}}
        write_sync(staged / "EXPORT_RECEIPT.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        if output.exists():
            output.rmdir()
        os.replace(staged, output)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microdata", type=Path, required=True)
    parser.add_argument("--baseline-software", type=Path, default=ROOT / "vendor")
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aggregate-reference", type=Path, default=ROOT / "vendor/aggregate_reference")
    args = parser.parse_args()
    try:
        receipt = export(args.microdata, args.baseline_software, args.protocol, args.output,
                         args.aggregate_reference)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": receipt["status"], "primary_n": receipt["primary_n"],
                      "target_n": receipt["target_n"], "output": str(args.output.resolve())}, indent=2))


if __name__ == "__main__":
    main()
