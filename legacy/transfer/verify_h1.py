#!/usr/bin/env python3
"""Verify the H1 software handoff; artificial rows never constitute empirical evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify(baseline_private=None):
    checks = []
    protocol_sha = sha(ROOT / "protocol/H1_PROTOCOL.json")
    assert protocol_sha == "f3d6536f0de1ccd09cb18f3e73a4a7071eeada16a3423cbfca0572285ae6fa72"
    checks.append({"check": "frozen protocol", "status": "PASS"})
    for name, directory in (("engine", ROOT / "engine"), ("extractor", ROOT / "extractor")):
        proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(directory),
                               "-p", "test_*.py", "-v"], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        checks.append({"check": name + " unit tests", "status": "PASS", "log": proc.stdout + proc.stderr})
    engine = load("h1_verify_engine", ROOT / "engine/holdout_engine.py")
    exporter = load("h1_verify_exporter", ROOT / "extractor/export_source_cells.py")
    frozen = exporter.load_frozen_executor(ROOT / "extractor/vendor")
    import pandas as pd
    rows = []
    for j, source in enumerate(("SYNTH_A", "SYNTH_B", "SYNTH_C")):
        for i, (state, sales, weight) in enumerate(((1, 1, 1), (2, 4, 2), (3, 2, 3), (4, 9, 2), (5, 7, 2))):
            rows.append({"firmid": 5*j+i+1, "country": source, "e6a": sales*(j+1),
                         "s7": 1, "base_wt": weight, **{f"ib9b{k}": int(k == state) for k in range(1, 6)}})
    labelled = exporter.add_event(frozen.prepare_full_frame(pd.DataFrame(rows)), frozen)
    data = engine.parse_csv(exporter.csv_bytes(exporter.aggregate(labelled)))
    train = {s: v for s, v in data.items() if s != "SYNTH_C"}
    lock = engine.fit(train, {s: s for s in train}, protocol_sha)
    report = engine.score(lock, {"SYNTH_C": data["SYNTH_C"]}, {"SYNTH_C": "SYNTH_C"},
                          protocol_sha, country_disjoint=True)
    assert report["scope"] == "SYNTHETIC_TEST_ONLY" and len(report["results"]) == 16
    for row in report["results"]:
        assert abs(float(sum(row[f"state_{i}_share_percent"] for i in range(1, 6))) - 100) < 1e-10
        assert row["expected_weighted_contacts"] > 0
    checks.append({"check": "artificial rows through frozen labels, exporter and held-out engine",
                   "status": "PASS", "source_policy_quota_rows": 16})
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "must_not_be_created"
        missing = subprocess.run([sys.executable, "-B", str(ROOT / "run_h1.py"), "--microdata",
                                  str(Path(tmp)/"absent.zip"), "--output", str(target)], capture_output=True)
        assert missing.returncode != 0 and not target.exists()
        invalid = Path(tmp) / "wrong.zip"
        invalid.write_bytes(b"invalid-original-input")
        wrong = subprocess.run([sys.executable, "-B", str(ROOT / "run_h1.py"), "--microdata",
                                str(invalid), "--output", str(target)], capture_output=True)
        assert wrong.returncode != 0 and not target.exists()
    checks.append({"check": "complete empirical pipeline refuses absent and wrong original input before outputs",
                   "status": "PASS", "cases": 2})
    if baseline_private:
        inventory = json.loads((ROOT / "work/data_forensics/INPUT_DISCOVERY.json").read_text())
        records = inventory["all_local_file_manifest"]
        for record in records:
            path = Path(baseline_private) / record["path"]
            assert path.is_file() and path.stat().st_size == record["size_bytes"] and sha(path) == record["sha256"], record["path"]
        checks.append({"check": "canonical baseline unchanged", "status": "PASS", "files": len(records)})
    return {"status": "PASS", "scope": "SOFTWARE_AND_BASELINE_QA_ONLY",
            "empirical_transfer_executed": False, "protocol_sha256": protocol_sha,
            "engine_sha256": sha(ROOT / "engine/holdout_engine.py"),
            "exporter_sha256": sha(ROOT / "extractor/export_source_cells.py"), "checks": checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-private", type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.baseline_private)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "scope": result["scope"], "receipt": str(args.receipt)}))
