# Technology measurement under fixed screening capacity

This directory contains the original pooled-capacity and coding-transfer analyses for *Which Firms Make the List? Technology Measurement under Fixed Screening Capacity* by Antonio Clim. It includes analysis code, tests, reported aggregates, an independent empirical verifier and plotting scripts. For the current conditional and acquisition analyses, start with the [repository README](../README.md).

## Evidence and allocation contracts

The original pooled analysis applies one expected weighted quota to the combined 14,412-establishment cohort. The transfer extension fills that quota separately within each test source. Its source/country averages and pooled ratios of source scores therefore answer a different allocation question. Do not substitute them for the original pooled 0.40 yield difference or 7.39-point composition shift.

The frozen protocol evaluates four quotas (20%, 35%, 50% and 75%), selects one of six contiguous three-group codings using training sources only and applies the selected coding unchanged in the target. It also excludes complete reporting countries, removing both India sources together, and evaluates the all-primary training choice in Burkina Faso and Cambodia. Previous pooled and broad-sample exposure makes this retrospective transfer, not prospective external validation.

Retained computational evidence records thirty-nine checks against the historical pooled aggregate references. A separate implementation reconstructed eligibility, weighted labels, source weights and row-wise allocations from the same original input. It confirmed all 416 private policy/quota rows, 64 summary rows and 24 training choices/locks, with maximum numerical discrepancy 2.27e-13. This is independent computation on the same sample. No sampling confidence interval, equivalence test, causal effect or universal coding recommendation is claimed.

## Plot the pooled results: current Figures S2 and S3

Run the following commands from `legacy/`, using the pinned environment documented at the repository root. Keep new outputs outside the repository. The plotting source retains its historical export stems; the current six-figure generator maps them to Figures S2 and S3:

```sh
python -m pip install -r requirements-figures.txt
python -B plot_capacity.py --results reported_results/pooled --output /private/new-pooled-figures
```

The reported results are under `reported_results/pooled` and `reported_results/deletion`. The command above reproduces graphical exports from reported numerical CSVs. For a new calculation directly from the original microdata, use the next route.

## Recompute pooled results directly from the original FAT input

```sh
python -m pip install -r requirements-analysis.txt
python -B run_raw_pooled.py --microdata /private/WLD_2019-2023_FAT_v01_M_CSV.zip --frozen-module transfer/extractor/vendor/upstream/run_e4_frozen_analysis_v1.0.2.py --protocol transfer/protocol/H1_PROTOCOL.json --deletion-core rebuild_x10_bounds.py --output /private/new-raw-pooled
python -B plot_capacity.py --results /private/new-raw-pooled/capacity --output /private/new-raw-pooled-figures
```

This route needs no private X04, X06, X07 or X10 input export. It checks the original ZIP/member identities and sample fingerprints, reconstructs the required event masses and uses the original numerical capacity and deletion-bound functions. It preserves the historical sensitivity-bound calculation rather than replacing it with a different raw-data analysis. `RAW_POOLED_README_EN.md` describes the exact scope and output checks. The separate archived-input route remains available in `run_capacity.py`; its four input exports stay private, and its embedded hash checks have not been weakened.

## Rebuild transfer tables and Figure S1 from publication aggregates

```sh
python -B transfer/build_transfer_tables.py --inputs reported_results/transfer --output /private/new-supplement-tables
python -B transfer/plot_transfer.py --csv reported_results/transfer/within_source_quota_50_percent.csv --output /private/new-transfer-figure
```

The first command rebuilds the source-mean, excluded-source and source-heterogeneity panels and the country summary CSV. The second plots directly from the fourteen-source CSV and exports the publication-sized `Figure_S1.png`, `Figure_S1.svg` and `Figure_S1.pdf`. It does not require private source-state cells or the full 416-row table. These are the current S1 filenames; `source_transfer` identifies earlier exports. The [figure directory](../figures/README.md) provides the current numbering and previews.

The low average three-group loss at half capacity is not a bound on individual-source loss. Brazil loses 1.89 cases per 100 expected weighted contacts at 75%. In Burkina Faso the ordered rules remain below the lottery at all four quotas; their equality at half capacity is mechanical because the quota stays within the manual state. These unfavourable findings are retained.

## Recompute empirical transfer from the original FAT input

Obtain the original World Bank archive through an appropriate access route and keep it outside this package. The expected container is `WLD_2019-2023_FAT_v01_M_CSV.zip`, SHA-256 `6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e`; its pooled CSV hash is independently checked. The survey DOI is [10.48529/assd-3j65](https://doi.org/10.48529/assd-3j65), not a DOI for this software.

```sh
python -m pip install -r requirements-analysis.txt
python -B transfer/run_transfer_from_raw.py --microdata /private/WLD_2019-2023_FAT_v01_M_CSV.zip --output /private/new-transfer-run
python -B transfer/verify_empirical_rows.py --microdata /private/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol transfer/protocol/H1_PROTOCOL.json --canonical-run /private/new-transfer-run --output /private/new-independent-check.json
```

The public route uses the independent raw-row implementation for eligibility, membership fingerprints, source-normalised weights and the inclusive source-relative 20th-percentile event. It formats the reconstructed aggregate masses to eighteen decimal places and passes them to the unchanged exact engine. All-primary fitting precedes scoring of the two excluded-primary targets. It compares numerical output with the supplied publication aggregates at absolute tolerance 1e-9. Provenance records differ from the canonical private run, so numerical agreement is reported rather than byte identity. The private canonical pipeline separately retains its completed thirty-nine reference checks. No missing private reference file is needed by the public raw-data route. The route writes private source-state aggregates and full results but no establishment identifiers, row predictions or raw extracts. Do not place those private outputs in a public repository. `PUBLIC_DATA_BOUNDARY_EN.md` specifies the included and excluded result levels.

## Implementation checks

```sh
python -B -m unittest discover -s transfer/engine -p 'test_*.py' -v
```

These 22 engine tests use artificial rows. The eleven tests of the historical canonical exporter are preserved with its source, but their private parity-reference fixtures are not distributed; all eleven passed in the complete private H2 snapshot. Synthetic tests are distinct from the actual empirical rerun and independent raw-data calculation. The old binary-only conditional example is retained under `historical/conditional_held_out`; it is not the current empirical transfer route.

The observed dependency versions and plotting environment are supplied. Byte identity was verified in the recorded Linux environment; native Windows execution has not been tested. Plot-library/font differences can change graphical bytes. No GitHub Actions, automatic data download, publication, DOI reservation or external messaging is part of any command.
