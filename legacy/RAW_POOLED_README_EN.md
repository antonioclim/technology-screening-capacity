# Direct reproduction from the original FAT ZIP

`run_raw_pooled.py` reproduces the original pooled fixed-capacity results and the retained-mixture recall bounds. Its only data input is the exact original FAT ZIP. It does not require the archived X04, X06, X07 or X10 CSVs. The frozen E4 Python module and H1 protocol remain required software inputs.

Run from `legacy/`, replacing the absolute input and output paths:

```sh
python run_raw_pooled.py --microdata "/path/to/WLD_2019-2023_FAT_v01_M_CSV.zip" --frozen-module transfer/extractor/vendor/upstream/run_e4_frozen_analysis_v1.0.2.py --protocol transfer/protocol/H1_PROTOCOL.json --deletion-core rebuild_x10_bounds.py --output "/path/to/new-local-output"
```

The command syntax can also be entered in PowerShell with Windows paths, but native Windows execution has not been tested. `python` must refer to the environment in which the package requirements are installed. `--capacity-core` can explicitly select `pooled_capacity_core.py`; otherwise the adapter loads its sibling file. All software paths can be supplied explicitly. The output directory must be new or empty.

The command checks the ZIP and pooled member hashes, the frozen loader hash, the H1 protocol hash, the 21,055-row/723-column raw shape and the primary/broad sample fingerprints. The primary sample must contain exactly 14,412 establishments across the 12 prescribed sources. The broad sample identity is checked at 14,818 rows and is not substituted into the pooled calculations.

For each of the five event quantiles (10%, 15%, 20%, 25% and 30%), the adapter uses the frozen source-local mean-one weights, stable ascending weighted threshold and inclusive ties. After retaining these frozen floating-point event labels, it represents pooled state and event masses as exact fractions for the original capacity arithmetic. It does not replace labels with another weighting scale or change the technology priority order.

The output contains:

- `capacity/`: the same eight numerical CSVs and a new truthful `result_summary.json`.
- `deletion/`: reconstructed retained-mixture recall bounds and their QA receipt.
- `locally_derived_inputs/`: three newly generated aggregate input tables for local inspection.
- `RAW_POOLED_RECEIPT.json`: raw and software identities, sample fingerprints, output readback counts and runtime versions.

The pooled calculation fills one expected weighted quota across the entire primary population. The source-transfer command fills a separate quota within each source. These allocations answer different questions.

The sensitivity CSV deliberately retains the original aggregate-information calculation: states 2 and 3 remain unresolved when forming the historical alternative-outcome bounds. Reconstructing the underlying event labels from raw data does not silently replace those bounds with a different analysis. The X10 calculation omits one source and evaluates the retained mixture; it is not performance in the excluded source. Neither route supplies sampling confidence intervals or establishes equivalence.

The new API preserves the original numerical functions. It does not call, spoof or weaken the archive-only `run_capacity.py` input hash checks. Its receipt records `microdata_accessed: true` and `x07_numeric_parity_checks: 0`; a fresh run does not inherit historical aggregate parity counts.

The private development audit also used `verify_raw_pooled.py` against archived references. That optional audit tool is not included here and is not required by the raw reproduction command. No private archive inputs are embedded in the distributed execution modules.

The command writes only to the chosen local directory. Access to the original data must comply with the provider's terms. Locally generating results does not grant redistribution rights.
