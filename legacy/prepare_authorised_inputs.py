"""Stage exact Paper E inputs from an authorised local R3 results directory."""
import argparse
from hashlib import sha256
from pathlib import Path

POOLED = {
    "X04_LOW_PERFORMANCE_THRESHOLD_GRID.csv": "7069e707e0b380e19c2a71c5d70c486a0612763c349dda9e45d9502aebb0e21d",
    "X06_TRANSITION_GROUP_DECOMPOSITION.csv": "b523df3653b407acbe6e56772b01605c5232530f484b776ac41fb631f232c83e",
    "X07_ALL_MONOTONE_CUTPOINT_CLASSIFICATION.csv": "4fb38483aacf0d8b327634b8fc88c1dc18555c3e1e656e1d51c5bb442053af7d",
}
DELETION = {
    "X10_LEAVE_ONE_SOURCE_OUT_CLASSIFICATION_RANGES.csv": "b0d693b2807f008f71f7aa67786c0dd073831d2635b8e7e3a74a12884f3a834a",
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r3-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.r3_results.is_dir():
        parser.error("--r3-results must be an existing directory")
    files = {}
    for name, expected in (POOLED | DELETION).items():
        candidates = [p for p in args.r3_results.rglob(name) if p.is_file()]
        if len(candidates) != 1:
            parser.error(f"{name}: expected one file, found {len(candidates)}")
        blob = candidates[0].read_bytes()
        actual = sha256(blob).hexdigest()
        if actual != expected:
            parser.error(f"{name}: exact SHA-256 mismatch ({actual}). Preserve the source bytes.")
        files[name] = blob
    try:
        args.output.mkdir()
    except FileExistsError:
        parser.error("--output must be a new directory")
    pooled = args.output / "pooled"
    pooled.mkdir()
    for name in POOLED:
        (pooled / name).write_bytes(files[name])
    manifest = "".join(f"{h}  {n}\n" for n, h in POOLED.items())
    (pooled / "SHA256SUMS.txt").write_bytes(manifest.encode("ascii"))
    for name in DELETION:
        (args.output / name).write_bytes(files[name])
    print("PASS_EXACT_ARCHIVED_INPUTS: four SHA-256 matches.")

if __name__ == "__main__":
    main()
