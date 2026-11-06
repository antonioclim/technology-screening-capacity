#!/usr/bin/env python3
"""Run the complete private transfer evaluation from the pinned original FAT ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
RAW_SHA = "6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e"
PROTOCOL_SHA = "80c5d6d9d69cbb38901ee1f169acc9d912ac11a3d1fb1604aa46037c6f3418bb"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    with Path(path).open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def run(microdata, output):
    microdata = Path(microdata).resolve()
    output = Path(output).resolve()
    if not microdata.is_file():
        raise ValueError("Original FAT input absent; no empirical evaluation executed")
    if sha(microdata) != RAW_SHA:
        raise ValueError("Original FAT input digest mismatch; no empirical evaluation executed")
    protocol = ROOT / "protocol/H1_PROTOCOL.json"
    if sha(protocol) != PROTOCOL_SHA:
        raise ValueError("Frozen H1 protocol digest mismatch")
    if output.exists():
        raise ValueError("Choose a new output directory")
    output.mkdir(parents=True)
    receipt = {"status": "RUNNING", "empirical_evaluation_completed": False,
               "started_at_utc": datetime.now(timezone.utc).isoformat(),
               "raw_container_sha256": RAW_SHA, "protocol_sha256": PROTOCOL_SHA,
               "orchestrator_sha256": sha(__file__), "python": platform.python_version(),
               "commands": [], "public_release_approved": False,
               "scope": "RETROSPECTIVE_TRANSFER_AFTER_PRIOR_POOLED_EXPOSURE"}
    receipt_path = output / "PIPELINE_RECEIPT.json"
    write_json(receipt_path, receipt)

    def execute(label, args):
        command = [sys.executable, "-B", *map(str, args)]
        proc = subprocess.run(command, text=True, capture_output=True)
        # Logs contain only local file paths and aggregate software diagnostics.
        (output / (label + ".log")).write_text(proc.stdout + proc.stderr, encoding="utf-8")
        receipt["commands"].append({"step": label, "exit_code": proc.returncode})
        write_json(receipt_path, receipt)
        if proc.returncode:
            raise RuntimeError("Pipeline step failed: " + label)

    try:
        data = output / "private_source_cells"
        execute("01_export", [ROOT / "extractor/export_source_cells.py", "--microdata", microdata,
                               "--protocol", protocol, "--output", data])
        engine = ROOT / "engine/holdout_engine.py"
        primary = ["--input", data / "primary_cells.csv", "--manifest", data / "primary_manifest.json",
                   "--protocol", protocol]
        lock = output / "ALL_PRIMARY_TRAINING_LOCK.json"
        execute("02_fit_all_primary", [engine, "fit", *primary, "--output", lock])
        # The training lock is written before excluded-source policy scoring.
        lock_before_scoring = sha(lock)
        execute("03_score_excluded_primary", [engine, "score", "--input", data / "excluded_primary_cells.csv",
                    "--manifest", data / "excluded_primary_manifest.json", "--protocol", protocol,
                    "--lock", lock, "--country-disjoint", "--output", output / "EXCLUDED_PRIMARY_TRANSFER.json"])
        if sha(lock) != lock_before_scoring:
            raise RuntimeError("Training lock changed during target scoring")
        execute("04_source_transfer", [engine, "crossvalidate", *primary, "--unit", "source",
                                        "--output", output / "SOURCE_TRANSFER.json"])
        execute("05_country_transfer", [engine, "crossvalidate", *primary, "--unit", "country",
                                         "--output", output / "COUNTRY_TRANSFER.json"])
        files = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob("*"))
                 if p.is_file() and p != receipt_path}
        receipt.update(status="EMPIRICAL_RETROSPECTIVE_TRANSFER_COMPLETED",
                       empirical_evaluation_completed=True,
                       completed_at_utc=datetime.now(timezone.utc).isoformat(),
                       all_primary_lock_file_sha256=lock_before_scoring, files_sha256=files,
                       limitation="No prospective external validity, causal policy effect, welfare claim or sampling confidence interval is established.")
        write_json(receipt_path, receipt)
    except Exception as exc:
        receipt.update(status="FAILED_NO_COMPLETED_EMPIRICAL_CLAIM", failure=str(exc))
        write_json(receipt_path, receipt)
        raise
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microdata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = run(args.microdata, args.output)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": receipt["status"], "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
