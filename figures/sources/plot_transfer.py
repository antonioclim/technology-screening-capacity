#!/usr/bin/env python3
"""Plot Figure S1 directly from the supplied fourteen-source aggregate CSV."""
import argparse
from pathlib import Path
from plot_supplement_transfer import plot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory")
    args.output.mkdir(parents=True)
    plot(args.csv.resolve(), args.output.resolve())
    print("PASS: Figure S1 exported as PNG, SVG and PDF from the aggregate CSV.")
