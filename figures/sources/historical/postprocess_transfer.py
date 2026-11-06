#!/usr/bin/env python3
"""Export private H2 tables and a plotted audit figure from frozen result JSON."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

ROUTES = (("source_holdout", "SOURCE_TRANSFER.json"),
          ("country_holdout", "COUNTRY_TRANSFER.json"),
          ("excluded_primary", "EXCLUDED_PRIMARY_TRANSFER.json"))
POLICIES = ("five_states", "digital", "population_lottery", "train_selected_three_block")
QUOTAS = ("0.20", "0.35", "0.50", "0.75")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def partition(cuts):
    edges = (0, *cuts, 5)
    return "|".join("".join(str(i) for i in range(a+1, b+1)) for a, b in zip(edges, edges[1:]))


def decimal_quota(q):
    return f"{float(Fraction(q)):.2f}"


def write_csv(path, rows, leading):
    fields = list(leading) + sorted({k for r in rows for k in r} - set(leading))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def source_metadata(input_dir):
    metadata = {}
    for role, file in (("primary", "primary_cells.csv"), ("excluded_primary", "excluded_primary_cells.csv")):
        with (input_dir/"private_source_cells"/file).open(encoding="utf-8-sig", newline="") as handle:
            cells = list(csv.DictReader(handle))
        for source in sorted({r["source"] for r in cells}):
            subset = [r for r in cells if r["source"] == source]
            total = sum(Fraction(r["weight_mass"]) for r in subset)
            manual = sum(Fraction(r["weight_mass"]) for r in subset if r["state"] == "1")
            metadata[source] = {"cohort_role": role, "eligible_n": sum(int(r["n"]) for r in subset),
                                "manual_weighted_share_percent": float(100*manual/total)}
    return metadata


def selection_row(role, fold, lock):
    objectives = sorted([(Fraction(o["max_mean_yield_loss_exact"]), tuple(o["cuts"])) for o in lock["objectives"]])
    chosen = tuple(lock["selected_cuts"])
    assert chosen == objectives[0][1]
    row = {"route": role, "held_out_unit": fold, "selected_partition": partition(chosen),
           "selected_cuts": json.dumps(chosen, separators=(",", ":")),
           "training_source_count": len(lock["training_sources"]),
           "training_country_count": len(lock["training_countries"]),
           "selected_max_mean_yield_loss": float(objectives[0][0]),
           "runner_up_partition": partition(objectives[1][1]),
           "objective_margin_to_runner_up": float(objectives[1][0]-objectives[0][0]),
           "lock_sha256": lock["lock_sha256"]}
    for objective in lock["objectives"]:
        row["objective_"+partition(objective["cuts"])] = float(Fraction(objective["max_mean_yield_loss_exact"]))
    return row


def export(input_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = output_dir/"tables"
    figures = output_dir/"figures"
    tables.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)
    metadata = source_metadata(input_dir)
    source_rows, summary_rows, selection_rows = [], [], []
    documents = {}
    for role, file in ROUTES:
        data = read_json(input_dir/file)
        documents[role] = data
        assert data["scope"] == "RETROSPECTIVE_TRANSFER"
        for original in data["results"]:
            row = {**original, "route": role}
            row["quota"] = decimal_quota(row["quota"])
            row["partition"] = partition(row["cuts"])
            row["cuts"] = json.dumps(row["cuts"], separators=(",", ":"))
            source_rows.append(row)
        for original in data.get("summary", []):
            summary_rows.append({**original, "quota": decimal_quota(original["quota"]), "route": role})
        for fold in data.get("folds", []):
            selection_rows.append(selection_row(role, fold["held_out_unit"], fold["lock"]))
    selection_rows.insert(0, selection_row("excluded_primary", "both_excluded_primary_sources", read_json(input_dir/"ALL_PRIMARY_TRAINING_LOCK.json")))
    assert len(source_rows) == 416 and len(summary_rows) == 64 and len(selection_rows) == 24
    write_csv(tables/"source_policy_quota_results.csv", source_rows, ("route", "source", "country", "quota", "policy", "partition", "cuts"))
    write_csv(tables/"transfer_summaries.csv", summary_rows, ("route", "aggregation", "quota", "policy"))
    write_csv(tables/"training_selections.csv", selection_rows, ("route", "held_out_unit", "selected_partition", "selected_cuts"))

    q50 = []
    for role in ("source_holdout", "excluded_primary"):
        subset = [r for r in source_rows if r["route"] == role and r["quota"] == "0.50"]
        for source in sorted({r["source"] for r in subset}):
            policies = {r["policy"]: r for r in subset if r["source"] == source}
            row = {"route": role, "source": source, "country": policies["five_states"]["country"],
                   **metadata[source], "quota": "0.50",
                   "selected_partition": policies["train_selected_three_block"]["partition"]}
            for policy in POLICIES:
                original = policies[policy]
                row[policy+"_yield_per_100_expected_contacts"] = original["cases_per_100_expected_contacts"]
                row[policy+"_yield_delta_vs_five"] = original["yield_delta_vs_five"]
                row[policy+"_composition_tv_vs_five_pp"] = original["composition_tv_vs_five_pp"]
                row[policy+"_yield_delta_vs_lottery"] = original["cases_per_100_expected_contacts"]-policies["population_lottery"]["cases_per_100_expected_contacts"]
                for state in range(1, 6):
                    row[policy+f"_state_{state}_share_percent"] = original[f"state_{state}_share_percent"]
            q50.append(row)
    assert len(q50) == 14
    write_csv(tables/"within_source_quota_50_percent.csv", q50, ("route", "source", "country", "cohort_role", "eligible_n", "quota", "selected_partition"))

    # The plotting routine reads its CSV, rather than taking in-memory results.
    plot(tables/"within_source_quota_50_percent.csv", figures)
    audit = {"status": "PASS", "scope": "EMPIRICAL_RESULT_FORMATTING_AND_PLOTTING_ONLY",
             "source_policy_quota_rows": len(source_rows), "summary_rows": len(summary_rows),
             "selection_rows": len(selection_rows), "q50_sources": len(q50),
             "figure_data_source": "tables/within_source_quota_50_percent.csv",
             "input_json_sha256": {f: hashlib.sha256((input_dir/f).read_bytes()).hexdigest() for _, f in ROUTES},
             "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "public_release_approved": False,
             "limitations": ["Within-source quotas differ from the original pooled quota.",
                             "Retrospective transfer after prior pooled exposure.",
                             "No confidence intervals or equivalence test."]}
    (output_dir/"PRESENTATION_QA.json").write_text(json.dumps(audit, indent=2)+"\n")
    return audit


def plot(csv_path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "svg.hashsalt": "PaperE-H2-transfer", "pdf.fonttype": 42})
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels = {"India_Wave2_New": "India, wave 2", "India": "India, wave 1", "Korea": "Republic of Korea",
              "Vietnam": "Viet Nam", "BurkinaFaso": "Burkina Faso"}
    digital = "#b35b17"
    three = "#087f8c"
    fig = plt.figure(figsize=(11.8, 10.4), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(4.4, 1.5))
    left = fig.add_subplot(grid[0, 0])
    right = fig.add_subplot(grid[0, 1], sharey=left)
    target = fig.add_subplot(grid[1, :])
    y = np.arange(len(rows))
    for ax in (left, right):
        ax.axhspan(11.5, 13.5, color="#eef2f4", zorder=0)
        ax.axhline(11.5, color="#83929c", linewidth=.8)
        ax.grid(axis="x", color="#dce2e5", linewidth=.6)
        ax.set_axisbelow(True)
        ax.set_ylim(13.65, -.65)
        ax.spines[["top", "right"]].set_visible(False)
    for policy, colour, offset, marker, label in (("digital", digital, -.13, "s", "Fixed digital boundary"),
            ("train_selected_three_block", three, .13, "o", "Three groups selected in training")):
        left.scatter([float(r[policy+"_yield_delta_vs_five"]) for r in rows], y+offset,
                     s=38, color=colour, marker=marker, label=label, zorder=3)
        right.scatter([float(r[policy+"_composition_tv_vs_five_pp"]) for r in rows], y+offset,
                      s=38, color=colour, marker=marker, zorder=3)
    left.axvline(0, color="#45535a", linewidth=.8)
    left.set_yticks(y, [labels.get(r["source"], r["source"]) for r in rows])
    right.tick_params(axis="y", labelleft=False)
    left.set_xlabel("Yield difference from five states\n(cases per 100 expected weighted contacts)")
    right.set_xlabel("Contact-composition distance from five states\n(total variation, percentage points)")
    left.set_title("A  Yield at a 50% quota in each source", loc="left", fontweight="bold", pad=12)
    right.set_title("B  Contact composition across the five states", loc="left", fontweight="bold", pad=12)
    left.set_xlim(-3.65, .4)
    right.set_xlim(-1.4, 38.5)
    # Absolute yield against the lottery prevents mechanical equality in Burkina
    # Faso from being mistaken for successful screening or informative compression.
    excluded = [r for r in rows if r["route"] == "excluded_primary"]
    styles = (("five_states", "#344550", "D", -.24, "Five states"),
              ("digital", digital, "s", -.08, "Fixed digital boundary"),
              ("train_selected_three_block", three, "o", .08, "Three groups selected in training"),
              ("population_lottery", "#8a2d66", "x", .24, "Population lottery"))
    for policy, colour, marker, offset, label in styles:
        target.scatter([float(r[policy+"_yield_per_100_expected_contacts"]) for r in excluded],
                       np.arange(2)+offset, color=colour, marker=marker, s=48, label=label, zorder=3)
    target.set_yticks([0, 1], [labels.get(r["source"], r["source"]) for r in excluded])
    target.set_ylim(1.55, -.55)
    target.set_xlim(14, 27)
    target.grid(axis="x", color="#dce2e5", linewidth=.6)
    target.spines[["top", "right"]].set_visible(False)
    target.set_xlabel("Cases per 100 expected weighted contacts")
    target.set_title("C  Absolute yield in the two sources outside the primary cohort", loc="left", fontweight="bold", pad=10)
    target.legend(loc="upper center", bbox_to_anchor=(.5, -.28), ncol=2, frameon=False, fontsize=9)
    target.annotate("15.54: all three ordered policies", (15.5383, 0), xytext=(15.05, .45), fontsize=8.5,
                    arrowprops={"arrowstyle": "-", "linewidth": .6}, ha="left")
    target.annotate("20.71: lottery", (20.7086, .24), xytext=(21.35, -.34), fontsize=8.5,
                    arrowprops={"arrowstyle": "-", "linewidth": .6}, ha="left")
    fig.suptitle("Yield and contact composition across survey sources", fontsize=15, fontweight="bold")
    for ext in ("png", "svg", "pdf"):
        metadata = {"Date": "2026-11-05"} if ext == "svg" else ({"CreationDate": None, "ModDate": None} if ext == "pdf" else None)
        buffer = io.BytesIO()
        fig.savefig(buffer, format=ext, dpi=300, metadata=metadata)
        payload = buffer.getvalue()
        target_file = output/f"H2_source_transfer_quota50.{ext}"
        descriptor, temporary = tempfile.mkstemp(prefix=".h2-figure-", dir=output)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target_file)
            directory = os.open(output, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        assert target_file.read_bytes() == payload
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.input_dir.resolve(), args.output_dir.resolve()), indent=2))
