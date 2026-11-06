# H4 private retrospective information-value pilot

This is a private research overlay. It preserves H3 and does not submit, publish, reserve a DOI, transfer to other people, run GitHub Actions or accept a cost. It introduces no mathematical proof or causal programme claim.

The input must be the original `WLD_2019-2023_FAT_v01_M_CSV.zip`, SHA-256 `6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e`. Keep the ZIP outside the package. The code independently authenticates the ZIP and pooled member, and requires the unchanged frozen E4 reader and H1 protocol as explicit software inputs. Those are not substitutes for lawful data access.

The tested environment is Python 3.12.14 on Linux with the versions in `requirements-h4.txt`. Native Windows execution has not been performed. Fitting runs with a one-thread BLAS limit. The L-BFGS solver is deterministic here and does not use the protocol seed as a source of random splits.

From this software directory, replacing the quoted paths:

```sh
python -B run_h4_pilot.py --microdata "/path/to/WLD_2019-2023_FAT_v01_M_CSV.zip" --frozen-e4 "/path/to/run_e4_frozen_analysis_v1.0.2.py" --h1-protocol "/path/to/H1_PROTOCOL.json" --protocol "../protocol/H4_PROTOCOL.json" --addendum "../protocol/H4_ADDENDUM_A01.json" --output "/path/to/new-private-output"
python -B summarise_h4.py --run "/path/to/new-private-output" --output "/path/to/new-private-summary"
```

The first command requires a new output directory. `--prepare-only` validates the cohorts without fitting or scoring policies. The ordinary command runs all six prespecified cohorts: planning, administration, finance, finance excluding the ambiguous count 99 and the two paired common-cohort objectives. Each has eleven country exclusions and an all-primary training fit applied to both secondary targets. All sixteen policies and four source-specific quotas are retained.

`COHORT_QA.json` fixes membership identities and event-label provenance before fitting. Planning retains the H1 labels defined on the 14,412-row MOST base before adoption matching. Administration labels use its own MOST base; it is a function-specific replication. Finance uses observed nonnegative integer d3c, with the exact 2,500,000 anomaly excluded, without a sales/employment or successful-borrower restriction. Its label is reported unmet borrowing for **production expansion**, not technology-investment finance or a treatment benefit. A01 uses identical rows for the two objectives and retains the original productivity labels.

Routine features are sector, establishment-start-year proxy, multi-establishment status and foreign ownership. Source, country, sales, outcomes, region identifiers and manager characteristics do not enter the predictor. Employment appears only in the declared size sensitivities. Fixed full categorical domains are encoded without dropping a category. Numeric medians and standardisation are fitted on training rows; an unscaled missing flag always accompanies every numeric variable. Country-balanced training weights sum to the training sample size. Evaluation weights have mean one within the matched source.

The fixed model is L2 logistic regression, C=1, L-BFGS, 2,000 iterations and tolerance 1e-8. The separate learned state ordering uses five pseudo-observations at the training weighted prevalence. Models never rank states or firms using held-out events. Every fold commits its fit record before target metrics, verifies target-event perturbation and aligned target-row reversal and fills the expected weighted quota using a common chance for a marginal tied score.

An initial run failed the strict row-reversal guard because one probability differed by 2.78e-17 under batch BLAS arithmetic. The failed status and initial source are preserved privately. The corrected predictor computes the same fitted linear model per row with `math.fsum` and a stable scalar sigmoid. It does not round scores, merge ties or alter fitting hyperparameters. The numerical-remediation receipt measures differences against the original pipeline and checks unchanged coefficients and allocations.

The main aggregate outputs are `source_policy_quota_results.csv`, `group_contact_results.csv`, `cross_target_allocation.csv` and `cross_target_group_differences.csv`. Fit locks, parameters, membership hashes and diagnostic receipts accompany them. No row records, establishment identifiers or prediction vectors are written. Detailed source/group outputs remain private. A01 allocation distance describes normalised **expected** contact mass, not overlap of realised lists.

The summary command averages the two India sources within country, then the eleven countries equally. Secondary targets remain outside primary means. It supplies all locked paired contrasts, ranges and signs, MAX/MOST group-share and within-group-rate differences and A01 objective comparisons. Exact floating-point sign counts are descriptive numerical counts, not significance or equivalence tests. No survey-valid confidence interval, welfare estimate or money saved is inferred.

The focused synthetic checks are:

```sh
python -B -m unittest discover -s . -p 'test_pilot_primitives.py' -v
```

The code does not auto-download raw data. Output files are written to a temporary file, flushed and fsynced, read back, atomically replaced and read back in full. A failed run keeps a non-PASS receipt. Full raw empirical reconstruction and independent verification are separate from the synthetic checks.
