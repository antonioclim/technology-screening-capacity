# Independent computational checks

The canonical engines and the independent implementations use the same lawful original FAT input and installed numerical libraries. Independent computation is not an independent dataset, formal proof or survey-valid inference. Keep every generated output outside this candidate and treat detailed source/group outputs as private.

The inherited coding-transfer verifier is `legacy/transfer/verify_empirical_rows.py`. After a transfer run:

```sh
python legacy/transfer/verify_empirical_rows.py --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol legacy/transfer/protocol/H1_PROTOCOL.json --canonical-run /absolute/new_complete_run/transfer --output /absolute/new_transfer_check.json
```

For H4, `conditional/independent/verify_h4_primary.py` independently fits B, B+MOST5 and B+MAX5 at the 50% source quota. The `--h1-cells` argument is a historical source-state parity reference, not an input to the new model fits. It may be supplied from the private archive or regenerated locally by the transfer route at `/absolute/new_complete_run/transfer/private_source_cells/primary_cells.csv`. The regenerate-and-check route is a computational comparison on the same input; it does not recreate an independent archived reference.

```sh
python conditional/independent/verify_h4_primary.py --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol conditional/protocol/H4_PROTOCOL.json --h1-cells /absolute/new_complete_run/transfer/private_source_cells/primary_cells.csv --canonical-run /absolute/new_complete_run/conditional_run --output /absolute/new_independent_primary
python conditional/independent/verify_h4_objective_distance.py --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol conditional/protocol/H4_PROTOCOL.json --addendum conditional/protocol/H4_ADDENDUM_A01.json --output /absolute/new_independent_objectives
```

For H5, the main raw verifier covers q=0.50 in all fourteen sources, with separate planning and same-firm cohorts. The diagnostic adds both functions together. The comparison expects these two output subdirectories to be named `raw_reestimation` and `both_diagnostic` under a new parent directory.

```sh
python followup/independent/verify_h5_raw.py --raw /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol followup/protocol/H5_PROTOCOL.json --receipt followup/protocol/H5_LOCK_RECEIPT.json --output /absolute/new_h5_independent/raw_reestimation
python followup/independent/verify_both_diagnostic.py --raw /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_h5_independent/both_diagnostic
python followup/independent/compare_h5.py --independent /absolute/new_h5_independent --canonical /absolute/new_complete_run/followup
```

The H4 verifier's original scope README and historical snapshot remain with that source. Their past completed-run receipts are retained in the private audit archive, rather than copied here as if newly executed results. H6 execution receipts report the commands actually run on the packaged copy. H5 independent group reconstruction excludes the both-function diagnostic; all four canonical quotas are covered by aggregate accounting, not by independent fitting at every quota.

## H7 acquisition and capacity diagnostics

`acquisition/independent/independent_h7.py` preserves the separately implemented allocation, query-band, pool, sector-fixed and inverse checks. Its relative source paths resolve within `acquisition/`; its original bytes are retained. Run synthetic numerical comparisons without microdata:

```sh
python acquisition/independent/independent_h7.py --synthetic --output /absolute/new_h7_synthetic_comparison.json
```

After a canonical acquisition rerun, independently rerun the 24 outer logistic fits and then compare the results:

```sh
python acquisition/independent/independent_h7.py --empirical --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --production /absolute/new_acquisition/acquisition --output /absolute/new_independent_acquisition
python acquisition/independent/independent_h7.py --compare --production /absolute/new_acquisition/acquisition --independent /absolute/new_independent_acquisition --output /absolute/new_h7_comparison.json
```

The separate procedure reuses the inherited raw reader, cohort constructor and logistic fitter. It implements allocation and capacity arithmetic separately. It does not independently rerun the inner models or the tree fits. Its full source has 224 independently regenerated logistic random repeats, not all 28,672 random allocations. It recalculates all saved random summaries and the country/equal-country accounting. Production and comparison outputs are private. Original H7 completed-run receipts remain in the private continuity archive and are not presented as new empirical evidence in this local preparation.
