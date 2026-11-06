#!/usr/bin/env python3
"""Check exported CSV values, clean rebuild determinism and figure file integrity."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from xml.etree import ElementTree

from PIL import Image
from pypdf import PdfReader


def run(input_dir, presentation_dir):
    spec = importlib.util.spec_from_file_location("h2_postprocess_qa", presentation_dir/"postprocess_transfer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rebuilt = presentation_dir/"rebuild_check"
    if rebuilt.exists():
        shutil.rmtree(rebuilt)
    module.export(input_dir, rebuilt)
    compared = []
    for folder in ("tables", "figures"):
        for original in sorted((presentation_dir/folder).iterdir()):
            assert original.read_bytes() == (rebuilt/folder/original.name).read_bytes(), str(original)
            compared.append(str(original.relative_to(presentation_dir)))
    shutil.rmtree(rebuilt)
    original_rows = []
    for role, filename in module.ROUTES:
        data = json.loads((input_dir/filename).read_text())
        original_rows.extend((role, row) for row in data["results"])
    with (presentation_dir/"tables/source_policy_quota_results.csv").open(encoding="utf-8-sig", newline="") as handle:
        formatted = list(csv.DictReader(handle))
    assert len(formatted) == len(original_rows) == 416
    max_error, numeric_checks = 0., 0
    for (role, original), row in zip(original_rows, formatted):
        assert role == row["route"] and original["source"] == row["source"]
        for key, value in original.items():
            if isinstance(value, (int, float)):
                numeric_checks += 1
                max_error = max(max_error, abs(float(row[key])-value))
    assert max_error == 0.
    figures = presentation_dir/"figures"
    pdf = figures/"H2_source_transfer_quota50.pdf"
    assert pdf.read_bytes().rstrip().endswith(b"%%EOF")
    reader = PdfReader(pdf)
    assert len(reader.pages) == 1
    assert "Matplotlib" in reader.metadata["/Creator"]
    with Image.open(figures/"H2_source_transfer_quota50.png") as image:
        image.verify()
    svg = figures/"H2_source_transfer_quota50.svg"
    ElementTree.fromstring(svg.read_bytes())
    qa = json.loads((presentation_dir/"PRESENTATION_QA.json").read_text())
    qa.update(numeric_csv_roundtrip_checks=numeric_checks, numeric_csv_roundtrip_max_error=max_error,
              byte_identical_clean_rebuild=compared, figure_format_integrity="PASS",
              png_visual_qa="PASS; full PNG and reduced overview inspected after legend correction",
              figure_numbers_assigned=False,
              figure_file_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(figures.iterdir())},
              artifact_incident={"initial_pdf_truncated_bytes":4753, "recovered_pdf_bytes_before_final_label_revision":30156,
                                 "current_pdf_bytes":pdf.stat().st_size,
                                 "cause_established":False,
                                 "remedy":"Regenerated exports via in-memory rendering and atomic fsynced writes; subsequent format and independent reread checks passed."})
    (presentation_dir/"PRESENTATION_QA.json").write_text(json.dumps(qa, indent=2)+"\n")
    return qa


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--presentation-dir", type=Path, required=True)
    args = parser.parse_args()
    qa = run(args.input_dir.resolve(), args.presentation_dir.resolve())
    print(json.dumps({"status":qa["status"], "numeric_checks":qa["numeric_csv_roundtrip_checks"],
                      "max_error":qa["numeric_csv_roundtrip_max_error"],
                      "byte_identical_rebuild_files":len(qa["byte_identical_clean_rebuild"])}))
