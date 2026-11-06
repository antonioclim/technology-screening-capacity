"""Plot the Paper E screening results with editable and accessible vector exports."""
import argparse
import csv
import math
import hashlib
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path

import xml.etree.ElementTree as etree
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

STYLES = {
    "Five states": ("#152b49", "-", 2.6),
    "Digital": ("#007c78", "--", 2.0),
    "Platform or mobile": ("#bd7225", "-.", 1.7),
    "Specialised": ("#794a97", (0, (4, 2, 1, 2)), 1.6),
    "Integrated": ("#af3d45", (0, (6, 3)), 1.8),
    "Population lottery": ("#555f6b", ":", 1.8),
}
STATE_LABELS = ["Manual", "Standard software", "Platform or mobile", "Specialised", "Integrated ERP"]
STATE_COLOURS = ["#263c59", "#87a8bb", "#e3e3e3", "#dcaa63", "#a75b47"]
STATE_HATCHES = ["", "///", "xxx", "...", "\\\\"]
FIGURE_TITLES = {
    "FIGURE_CAPACITY": "Expected yield at equal weighted contact capacity",
    "FIGURE_LIST_COMPOSITION": "Composition of expected weighted contacts at half coverage",
}
FIGURE_DESCRIPTIONS = {
    "FIGURE_CAPACITY": (
        "Screening rules share the same expected weighted coverage. At 50% coverage, "
        "the five-state and digital rules yield 24.59 and 24.19 cases per 100 expected "
        "weighted contacts. The lower panel compares the five-state rule with digital, "
        "integrated and retrospectively selected best binary rules. Line patterns and markers "
        "distinguish those comparisons."
    ),
    "FIGURE_LIST_COMPOSITION": (
        "Four stacked bars show the share of expected weighted contacts by original technology "
        "state at 50% expected weighted coverage. Both the full and digital rules allocate "
        "68.13% to manual planners. Digital coding shifts 7.39 percentage points from standard "
        "software to three more advanced states. Patterns distinguish the five states. "
        "A table below the bars gives each share as a percentage."
    ),
}


def read_rows(path, required):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"{path.name}: missing required columns")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name}: no data rows")
    return rows


def number(text, field):
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: expected a finite number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{field}: expected a finite number")
    return value


def load_results(results):
    rows = read_rows(results / "capacity_curves.csv", {
        "rule", "coverage", "cases_per_100_contacts", "loss_vs_five_states_per_100_eligible",
    })
    series = {}
    for row in rows:
        rule = row["rule"]
        if not rule:
            raise ValueError("capacity_curves.csv: empty rule label")
        series.setdefault(rule, {})
        quota = number(row["coverage"], "coverage")
        if not 0 <= quota <= 1:
            raise ValueError("capacity_curves.csv: coverage outside [0, 1]")
        if quota in series[rule]:
            raise ValueError(f"capacity_curves.csv: duplicate rule and coverage for {rule!r}")
        row["quota"] = quota
        row["loss"] = number(row["loss_vs_five_states_per_100_eligible"], "loss")
        if quota == 0:
            if row["cases_per_100_contacts"]:
                raise ValueError("capacity_curves.csv: yield at zero coverage must be empty")
            row["yield"] = None
        else:
            row["yield"] = number(row["cases_per_100_contacts"], "yield")
        series[rule][quota] = row
    if not set(STYLES).issubset(series):
        raise ValueError("capacity_curves.csv: a plotted screening rule is missing")
    quotas = set(series["Five states"])
    if not {0.0, 1.0}.issubset(quotas):
        raise ValueError("capacity_curves.csv: endpoint coverage rows are missing")
    if any(set(points) != quotas for points in series.values()):
        raise ValueError("capacity_curves.csv: rules must have the same coverage grid")
    ordered = {rule: [series[rule][q] for q in sorted(quotas)] for rule in STYLES}

    composition = read_rows(results / "list_composition.csv", {
        "rule", "coverage", "state", "share_of_expected_contacts_percent",
    })
    shares = {}
    seen = set()
    composition_groups = {}
    for row in composition:
        rule = row["rule"]
        if rule not in STYLES:
            raise ValueError(f"list_composition.csv: unknown rule {rule!r}")
        quota = number(row["coverage"], "coverage")
        state_value = number(row["state"], "state")
        if quota not in quotas or state_value not in range(1, 6):
            raise ValueError("list_composition.csv: invalid coverage or state")
        state = int(state_value)
        key = rule, quota, state
        if key in seen:
            raise ValueError("list_composition.csv: duplicate rule, coverage and state")
        seen.add(key)
        share = number(row["share_of_expected_contacts_percent"], "contact share")
        if not 0 <= share <= 100:
            raise ValueError("list_composition.csv: contact share outside [0, 100]")
        composition_groups.setdefault((rule, quota), {})[state] = share
        if quota == .5:
            shares[rule, state] = share
    for (rule, quota), states in composition_groups.items():
        if set(states) != set(range(1, 6)):
            raise ValueError(f"list_composition.csv: incomplete states for {rule!r} at {quota}")
        if not math.isclose(sum(states.values()), 100, abs_tol=1e-8):
            raise ValueError(f"list_composition.csv: shares must sum to 100 for {rule!r} at {quota}")
    for rule in ("Five states", "Digital", "Integrated", "Population lottery"):
        if any((rule, state) not in shares for state in range(1, 6)):
            raise ValueError(f"list_composition.csv: incomplete half-coverage states for {rule!r}")
        if not math.isclose(sum(shares[rule, state] for state in range(1, 6)), 100, abs_tol=1e-8):
            raise ValueError(f"list_composition.csv: half-coverage shares must sum to 100 for {rule!r}")
    return ordered, shares



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

def save(fig, stem):
    title = FIGURE_TITLES[stem.name]
    description = FIGURE_DESCRIPTIONS[stem.name]
    svg_buffer = BytesIO()
    fig.savefig(svg_buffer, format="svg", metadata={"Date": None, "Title": title,
                "Description": description, "Creator": f"Matplotlib {mpl.__version__}"})
    for prefix, uri in (("", "http://www.w3.org/2000/svg"),
                        ("xlink", "http://www.w3.org/1999/xlink"),
                        ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
                        ("cc", "http://creativecommons.org/ns#"),
                        ("dc", "http://purl.org/dc/elements/1.1/")):
        etree.register_namespace(prefix, uri)
    tree = etree.parse(BytesIO(svg_buffer.getvalue()), etree.XMLParser(target=etree.TreeBuilder(insert_comments=True)))
    root = tree.getroot()
    ns = "{http://www.w3.org/2000/svg}"
    title_node = etree.Element(ns + "title", {"id": "figure-title"})
    title_node.text = title
    desc_node = etree.Element(ns + "desc", {"id": "figure-description"})
    desc_node.text = description
    root.insert(0, desc_node)
    root.insert(0, title_node)
    root.set("role", "img")
    root.set("aria-labelledby", "figure-title figure-description")
    edited_svg = BytesIO()
    tree.write(edited_svg, encoding="utf-8", xml_declaration=True)
    png_buffer = BytesIO()
    fig.savefig(png_buffer, format="png", dpi=300, metadata={
        "Software": f"Matplotlib {mpl.__version__}", "Title": title,
        "Description": description, "Author": "Antonio Clim",
    })
    pdf_buffer = BytesIO()
    fig.savefig(pdf_buffer, format="pdf", metadata={
        "Title": title, "Subject": description, "Author": "Antonio Clim",
        "Creator": f"Matplotlib {mpl.__version__}", "CreationDate": None, "ModDate": None,
    })
    plt.close(fig)
    return {ext: atomic_export(stem.with_suffix(ext), data) for ext, data in (
        (".svg", edited_svg.getvalue()), (".png", png_buffer.getvalue()), (".pdf", pdf_buffer.getvalue()))}


def plot(results, out):
    series, subset = load_results(results)
    out.mkdir(parents=False, exist_ok=False)
    mpl.rcParams.update({
        "font.size": 10, "font.family": "DejaVu Sans", "axes.spines.top": False,
        "axes.spines.right": False, "axes.labelcolor": "#24364b", "text.color": "#172b43",
        "svg.fonttype": "none", "svg.hashsalt": "papere-capacity-phase2",
        "pdf.fonttype": 42, "hatch.linewidth": .55,
    })
    fig, axes = plt.subplots(2, 1, figsize=(8.3, 6.4), sharex=True,
                             gridspec_kw={"height_ratios": [2.1, 1.15]})
    fig.subplots_adjust(left=.16, right=.965, bottom=.18, top=.88, hspace=.22)
    fig.text(.16, .963, "The value of recording five technology states", weight="bold", size=15)
    fig.text(.16, .918, "Production planning · common weighted FAT sample", size=10)
    top, bottom = axes
    x = [100 * r["quota"] for r in series["Five states"]]
    for name, (colour, line, width) in STYLES.items():
        selected = [r for r in series[name] if r["yield"] is not None]
        top.plot([100 * r["quota"] for r in selected], [r["yield"] for r in selected],
                 label=name, color=colour, linestyle=line, linewidth=width)
    top.set_ylabel("Cases per 100\nexpected contacts")
    top.legend(loc="upper right", frameon=False, ncols=2, fontsize=8)
    for name, label, colour, line, marker in (
        ("Digital", "Versus digital", "#007c78", "--", "o"),
        ("Integrated", "Versus integrated", "#af3d45", "-.", "s"),
    ):
        bottom.plot(x, [r["loss"] for r in series[name]], color=colour, linewidth=1.65,
                    linestyle=line, marker=marker, markersize=3.5, markevery=max(1, len(x)//12),
                    markerfacecolor="white", markeredgewidth=.85, label=label)
    binary = [series[k] for k in list(STYLES)[1:-1]]
    bottom.plot(x, [min(r["loss"] for r in points) for points in zip(*binary)],
                color="#152b49", linewidth=2.0, linestyle="-", zorder=1.5,
                label="Versus retrospective best binary")
    bottom.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="none", fontsize=8)
    bottom.set_xlabel("Expected weighted share contacted (%)")
    bottom.set_ylabel("Extra cases per 100\neligible establishments")
    bottom.yaxis.set_major_locator(MaxNLocator(nbins=4))
    for axis in axes:
        axis.grid(axis="y", color="#e0e6ed", linewidth=.75)
        axis.set_axisbelow(True)
        axis.set_xlim(0, 100)
    fig.text(.16, .044, "Point estimates. Equal contact probabilities within the marginal group.",
             color="#4f6377", size=8.5)
    exports = {"FIGURE_CAPACITY": save(fig, out / "FIGURE_CAPACITY")}

    rules = ["Five states", "Digital", "Integrated", "Population lottery"]
    fig, ax = plt.subplots(figsize=(8.3, 5.6))
    fig.subplots_adjust(left=.22, right=.965, bottom=.47, top=.82)
    fig.text(.22, .955, "Who appears on the list?", weight="bold", size=15)
    fig.text(.22, .895, "Composition at 50% expected weighted coverage", size=10)
    for y, rule in enumerate(rules):
        left = 0
        for state, (colour, hatch) in enumerate(zip(STATE_COLOURS, STATE_HATCHES), 1):
            width = subset[rule, state]
            ax.barh(y, width, left=left, color=colour, hatch=hatch, height=.62,
                    edgecolor="#283441", linewidth=.45)
            if width >= 12:
                ax.text(left + width / 2, y, f"{width:.1f}%", ha="center", va="center", fontsize=9,
                        color="white" if state == 1 else "#142333", weight="bold",
                        bbox={"facecolor":colour, "edgecolor":"none", "pad":.7})
            left += width
    ax.set_yticks(range(len(rules)), rules)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of expected weighted contacts (%)")
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    table_ax = fig.add_axes([.16, .055, .81, .235])
    table_ax.axis("off")
    table = table_ax.table(
        cellText=[[f"{subset[rule, state]:.2f}" for state in range(1,6)] for rule in rules],
        rowLabels=rules, colLabels=["Manual", "Standard\nsoftware", "Platform\nor mobile", "Specialised", "Integrated\nERP"],
        cellLoc="right", rowLoc="left", bbox=[.22,0,.78,1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#d2d9df")
        cell.set_linewidth(.35)
        cell.set_facecolor("white")
        if row == 0:
            cell.set_text_props(weight="bold", ha="center")
        if col == -1:
            cell.set_text_props(ha="left")
    handles = [mpl.patches.Patch(facecolor=c, hatch=h, edgecolor="#283441", linewidth=.45, label=s)
               for c,h,s in zip(STATE_COLOURS, STATE_HATCHES, STATE_LABELS)]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(.22,.36), ncols=3,
               frameon=False, fontsize=8.5, borderaxespad=0)
    fig.text(.16,.014,"Shares in the table are percentages. Rounded entries may not sum to 100.",
             color="#4f6377",size=8)
    exports["FIGURE_LIST_COMPOSITION"] = save(fig, out / "FIGURE_LIST_COMPOSITION")
    atomic_export(out / "PLOT_WRITE_QA.json", (json.dumps({"status": "PASS", "scope": "IN_MEMORY_RENDER_ATOMIC_FSYNCED_WRITE_FULL_READBACK", "exports": exports}, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.results, args.output)
