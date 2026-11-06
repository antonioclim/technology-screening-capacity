# Independent H5 verification — original layout

These instructions preserve the original H5 directory layout. For the current package, use the H5 commands in [INDEPENDENT_CHECKS_EN.md](../../INDEPENDENT_CHECKS_EN.md) from the package root. The `../empirical/` paths below belong to the original layout and are not paths in the current payload.

The programs in this directory independently implement cohort preparation, anchored planning labels, training weights, preprocessing, fixed logistic/tree fits and expected-contact allocation. They do not import scientific functions from the canonical H4/H5 engine. They use the same installed numerical libraries.

Run from a new working directory with the original authenticated FAT ZIP supplied separately. The example paths assume this directory is beside `empirical`. Use new output directories; the programs refuse to overwrite previous results.

```bash
python3 -B verify_h5_raw.py --raw /path/to/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol ../empirical/protocol/H5_PROTOCOL.json --receipt ../empirical/protocol/H5_LOCK_RECEIPT.json --output raw_reestimation_NEW
python3 -B verify_both_diagnostic.py --raw /path/to/WLD_2019-2023_FAT_v01_M_CSV.zip --output both_diagnostic_NEW
```

`compare_h5.py` expects subdirectories named `raw_reestimation` and `both_diagnostic` under its `--independent` argument. Copy the new outputs to a new comparison parent with these names if rerunning.

```bash
python3 -B compare_h5.py --independent /path/to/new_comparison_parent --canonical ../empirical/results
```

Independent raw fits cover q=0.50 only, all 14 sources and all 12 predeclared cohort/policy/learner combinations. Independent group metrics exclude the both-function diagnostic. Aggregate accounting from canonical outputs covers all four quotas. No survey inference, prospective validation, formal proof or native Windows execution is claimed.

The protocol receipt documents a local lock before these new fits. H5 was designed after H4 results were known. This is not an independent preregistration. No original microdata, individual identifiers or prediction vectors are distributed here.
