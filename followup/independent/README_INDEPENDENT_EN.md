# Independent function and learner checks

These programs independently implement cohort preparation, anchored planning labels, training weights, preprocessing, fixed logistic/tree fits and expected-contact allocation. They do not import scientific functions from the canonical H4/H5 engine; both implementations use the same installed numerical libraries.

## Run from the repository root

Supply the authenticated original FAT ZIP separately. Use new output directories outside the repository:

```sh
python -B followup/independent/verify_h5_raw.py --raw /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol followup/protocol/H5_PROTOCOL.json --receipt followup/protocol/H5_LOCK_RECEIPT.json --output /absolute/new_h5_independent/raw_reestimation
python -B followup/independent/verify_both_diagnostic.py --raw /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_h5_independent/both_diagnostic
python -B followup/independent/compare_h5.py --independent /absolute/new_h5_independent --canonical /absolute/new_complete_run/followup
```

The first two commands create the `raw_reestimation` and `both_diagnostic` subdirectories expected by the comparison; no manual copying or renaming is needed. The canonical path in the third command is the follow-up output of a completed top-level run. See [Independent checks](../../INDEPENDENT_CHECKS_EN.md) for that sequence.

## Scope

Independent raw fits cover q=0.50, all fourteen sources and all twelve declared cohort/policy/learner combinations. Independent group metrics exclude the both-function diagnostic. Aggregate accounting from canonical outputs covers all four quotas. This does not establish survey inference, prospective validation or native Windows acceptance.

The original lock records the H5 specification before those fits, after H4 results were known. The [public projection record](../../docs/PROTOCOL_PROJECTIONS.md) distinguishes that historical lock from later administrative changes. Original microdata, individual identifiers and prediction vectors are not distributed.
