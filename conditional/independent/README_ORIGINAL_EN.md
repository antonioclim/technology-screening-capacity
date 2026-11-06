# Independent H4 computation

This folder contains a separate implementation of the H4 primary comparison. It imports no H4 analysis computation module. It reads the authenticated original FAT archive, rebuilds eligibility and frozen event labels, encodes the declared features and fits the same prespecified scikit-learn logistic model family independently.

The independent scope is deliberately explicit:

- All six H4 cohort memberships, source counts and primary membership hashes are reconstructed from the original rows.
- The original H1 planning base and source-state count/event/weight summaries are checked against the private historical reference.
- Planning B, B+MOST5 and B+MAX5 are separately fitted in all eleven country exclusions, then evaluated at a 50% quota in all twelve primary sources. This is 33 independent fits and 36 source/policy scores.
- Sector and employment-group masses, contact shares and within-group contact rates are independently calculated for those same primary comparisons.
- The paired common-cohort productivity and finance objectives are independently fitted for the same three model families at 50%: 66 additional fits. The reported distance concerns normalised expected-contact allocations, not realised lists.
- Event prevalence and lottery accounting can be verified across all six cohorts, fourteen primary/secondary sources and four quotas without fitting additional models.

The final comparison script checks numerical agreement at absolute tolerance 1e-7. This is far smaller than the displayed screening-yield units, but it is a numerical tolerance rather than a confidence level. It is not a claim to have independently re-estimated all sixteen model families at all quotas.

All intermediate data, establishment identifiers, individual predictions and contact probabilities remain in process memory. Saved files contain aggregate results and fit receipts only. Generated detailed group aggregates are private, including small groups. Keep those output directories outside the public repository. This source directory contains verification programs, not the generated private outputs.

## Commands

The examples below run from `conditional/independent/`. Supply the original ZIP, a separately authorised or locally regenerated H1 parity reference and a new output directory for each replay. For the complete sequence with the current repository paths, use [Independent checks](../../INDEPENDENT_CHECKS_EN.md).

```sh
python3 -B verify_h4_primary.py --microdata /private/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol ../protocol/H4_PROTOCOL.json --h1-cells /private/primary_cells.csv --output /private/new-independent-primary
python3 -B verify_h4_objective_distance.py --microdata /private/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol ../protocol/H4_PROTOCOL.json --addendum ../protocol/H4_ADDENDUM_A01.json --output /private/new-independent-objectives
python3 -B verify_h4_cohorts.py --microdata /private/WLD_2019-2023_FAT_v01_M_CSV.zip --protocol ../protocol/H4_PROTOCOL.json --canonical-run /private/completed-H4-run --output /private/new-cohort-check.json --include-lottery
python3 -B compare_completed_h4.py --canonical-run /private/completed-H4-run --primary-run /private/new-independent-primary --paired-run /private/new-independent-objectives --output /private/new-comparison.json
python3 -B test_independent_primitives.py
```

`primary_cells.csv` is the preserved H1/H2 primary source-state reference in the private H3 archive. It is used for historical parity only; it is not a substituted input to the new model fits. The data providers' access and redistribution terms remain unchanged.

Earlier replay directories and the superseded verifier snapshot are retained in the private research archive. Historical receipts record the scope and status at the time of each execution; they are not presented as tests performed on the current repository snapshot.

This is independent computation on the same authenticated dataset and with the same declared modelling library, not independent external data, prospective validation, formal verification, causal inference or a new mathematical proof. Native Windows execution has not been tested.
