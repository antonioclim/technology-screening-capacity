#!/usr/bin/env python3
"""Plot Supplement Figure S1 at its intended 6.52-inch publication width.

Consumes the released 50% source-level reporting CSV: no state-share columns,
raw records or source-state event cells are required by this plotting program.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path



def validate_export(data, suffix):
    """Reject incomplete renderer buffers before any final filename is written."""
    if not data:
        raise OSError("Empty graphical export")
    if suffix == ".svg":
        import xml.etree.ElementTree as ET
        if ET.fromstring(data).tag != "{http://www.w3.org/2000/svg}svg":
            raise OSError("Invalid SVG root")
    elif suffix == ".png":
        from PIL import Image
        with Image.open(BytesIO(data)) as image:
            image.verify()
    elif suffix == ".json":
        json.loads(data)
    elif suffix == ".pdf":
        import re
        if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
            raise OSError("Incomplete PDF header or end marker")
        matches = list(re.finditer(rb"startxref\s+(\d+)\s+%%EOF\s*$", data))
        if len(matches) != 1:
            raise OSError("Missing final PDF cross-reference pointer")
        offset = int(matches[0].group(1))
        if not 0 < offset < len(data) or data[offset:offset + 4] != b"xref":
            raise OSError("Invalid PDF cross-reference offset")
    else:
        raise ValueError("Unsupported graphical format: " + suffix)


def atomic_export(path, data):
    """Commit an in-memory render atomically, then verify every stored byte."""
    validate_export(data, path.suffix)
    descriptor, temporary_name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            written = handle.write(data)
            if written != len(data):
                raise OSError("Short graphical write: " + str(path))
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != data:
            raise OSError("Temporary graphical readback differs: " + str(path))
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        stored = path.read_bytes()
        if stored != data:
            raise OSError("Final graphical readback differs: " + str(path))
        validate_export(stored, path.suffix)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "atomic_replace": True, "file_fsynced": True, "full_readback_equal": True}


def plot(csv_path: Path, output_dir: Path):
    # A failed rerun must not leave an earlier success receipt in place.
    qa_path = output_dir / "FIGURE_S1_QA.json"
    if qa_path.exists():
        qa_path.unlink()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 14 and {r["quota"] for r in rows} == {"0.50"}
    assert sum(r["route"] == "source_holdout" for r in rows) == 12
    assert sum(r["route"] == "excluded_primary" for r in rows) == 2
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = {"India_Wave2_New": "India, wave 2", "India": "India, wave 1",
              "Korea": "Republic of Korea", "Vietnam": "Viet Nam", "BurkinaFaso": "Burkina Faso"}
    colours = {"digital": "#a24b0d", "train_selected_three_block": "#007b83",
               "five_states": "#344550", "population_lottery": "#8a2d66"}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5,
                         "axes.titlesize": 9, "axes.labelsize": 8.5,
                         "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
                         "legend.fontsize": 8.5, "pdf.fonttype": 42, "svg.fonttype": "none",
                         "svg.hashsalt": "PaperE-H3-Supplement-S1"})
    # At native width the smallest labels are 8.5pt, including legends.
    fig = plt.figure(figsize=(6.52, 7.15))
    grid = fig.add_gridspec(2, 2, height_ratios=(4.4, 1.4),
                           left=.205, right=.98, bottom=.14, top=.95,
                           wspace=.16, hspace=.55)
    left = fig.add_subplot(grid[0, 0])
    right = fig.add_subplot(grid[0, 1], sharey=left)
    target = fig.add_subplot(grid[1, :])
    y = np.arange(len(rows))
    for ax in (left, right):
        ax.axhspan(11.5, 13.5, color="#eef2f4", zorder=0)
        ax.axhline(11.5, color="#83929c", linewidth=.6)
        ax.grid(axis="x", color="#dce2e5", linewidth=.5)
        ax.set_axisbelow(True)
        ax.set_ylim(13.65, -.65)
        ax.spines[["top", "right"]].set_visible(False)
    for policy, offset, marker in (("digital", -.13, "s"), ("train_selected_three_block", .13, "o")):
        left.scatter([float(r[policy+"_yield_delta_vs_five"]) for r in rows], y+offset,
                     s=22, color=colours[policy], marker=marker, zorder=3)
        right.scatter([float(r[policy+"_composition_tv_vs_five_pp"]) for r in rows], y+offset,
                      s=22, color=colours[policy], marker=marker, zorder=3)
    left.axvline(0, color="#45535a", linewidth=.6)
    left.set_yticks(y, [labels.get(r["source"], r["source"]) for r in rows])
    left.tick_params(axis="y", length=0, pad=4)
    right.tick_params(axis="y", left=False, labelleft=False)
    left.set_xlabel("Yield difference from five states\n(cases per 100 expected\nweighted contacts)")
    right.set_xlabel("Composition distance from five states\n(total variation, percentage points)")
    left.set_title("A  Yield at a separate\n50% quota in each source", loc="left", fontweight="bold", pad=8)
    right.set_title("B  Contact composition\nacross the five states", loc="left", fontweight="bold", pad=8)
    left.set_xlim(-3.7, .45)
    left.set_xticks([-3, -2, -1, 0])
    right.set_xlim(-1.5, 38.5)
    right.set_xticks([0, 10, 20, 30])

    excluded = [r for r in rows if r["route"] == "excluded_primary"]
    styles = (("five_states", "D", -.24, "Five states"),
              ("digital", "s", -.08, "Fixed digital boundary"),
              ("train_selected_three_block", "o", .08, "Three groups selected in training"),
              ("population_lottery", "x", .24, "Population lottery"))
    for policy, marker, offset, label in styles:
        target.scatter([float(r[policy+"_yield_per_100_expected_contacts"]) for r in excluded],
                       np.arange(2)+offset, color=colours[policy], marker=marker,
                       s=28, label=label, zorder=3)
    target.set_yticks([0, 1], [labels.get(r["source"], r["source"]) for r in excluded])
    target.set_ylim(1.45, -.5)
    target.set_xlim(14, 27)
    target.set_xticks([15, 18, 21, 24, 27])
    target.tick_params(axis="y", length=0, pad=4)
    target.grid(axis="x", color="#dce2e5", linewidth=.5)
    target.spines[["top", "right"]].set_visible(False)
    target.set_xlabel("Cases per 100 expected weighted contacts")
    target.set_title("C  Absolute yield outside the primary cohort", loc="left", fontweight="bold", pad=8)
    handles = [Line2D([], [], color=colours[p], marker=m, linestyle="None", markersize=5,
                      label=lab) for p, m, _, lab in styles]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.53, .01),
               ncol=2, frameon=False, columnspacing=1.2, handletextpad=.4)
    exports = {}
    for ext in ("png", "svg", "pdf"):
        metadata = ({"Date": "2026-11-05"} if ext == "svg" else
                    {"CreationDate": None, "ModDate": None} if ext == "pdf" else None)
        buffer = BytesIO()
        fig.savefig(buffer, format=ext, dpi=300, metadata=metadata)
        exports[ext] = atomic_export(output_dir / f"Figure_S1.{ext}", buffer.getvalue())
    plt.close(fig)
    report = {"status": "PASS", "data_source_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
              "source_rows": len(rows), "native_width_inches": 6.52,
              "native_height_inches": 7.15, "minimum_text_size_pt": 8.5,
              "data_required": "source-level yields, yield differences and composition distances at 50%",
              "state_share_columns_required": False, "generative_image_model_used": False,
              "write_integrity_scope": "IN_MEMORY_RENDER_ATOMIC_FSYNCED_WRITE_FULL_READBACK", "exports": exports}
    atomic_export(qa_path, (json.dumps(report, indent=2)+"\n").encode("utf-8"))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(plot(args.csv, args.output_dir), indent=2))
