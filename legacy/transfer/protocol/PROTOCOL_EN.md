# Paper E source transfer evaluation

Protocol date: 5 November 2026. Governing machine-readable contract: `H1_PROTOCOL.json`, SHA-256 `80c5d6d9d69cbb38901ee1f169acc9d912ac11a3d1fb1604aa46037c6f3418bb`. This protocol was fixed before newly obtaining or scoring source-specific event masses in this extension. It follows substantial prior pooled exploration. Its local digest is not independent preregistration.

## Research question and evidence

At the same expected weighted screening capacity, does compressing the five recorded technology states preserve the yield of contact while changing the composition of the contact list when the coding is applied to a source excluded from its selection?

The study concerns the information used to construct a screening list. Yield means cases of a source-relative low-sales-per-worker event per 100 expected weighted contacts. A change in the composition of the contact list is reported as a change in who is contacted. It has no assumed welfare, fairness or treatment-effect sign.

The primary fixed comparison is digital versus five-state allocation at 50% capacity. The population lottery provides a prevalence benchmark. Selection among three-block codings is a secondary, explicitly adaptive comparison. All four locked quotas, 20%, 35%, 50% and 75%, are reported. A maximum over four quotas does not establish a bound over the entire capacity curve.

## Prior exposure and transfer routes

All 12 primary sources contributed to the historical pooled analyses. The pooled three-block winner `1|23|45` and its observed pooled performance are already known. They cannot be made unselected by announcing a freeze now.

Three routes have different interpretations:

1. Leave one source out of the 12-source development cohort, select a coding using the other 11 and evaluate the excluded source. This is retrospective source transfer of a selection procedure after prior pooled exposure.
2. Leave one reporting country out of the 11-country development cohort. Both Indian sources are excluded together in the India fold. This checks dependence on training and testing in the same reporting country; it does not create a later wave or a new country.
3. Select once on all 12 primary sources and apply that coding unchanged to both Burkina Faso and Cambodia. These sources were excluded from the primary cohort because of low sales coverage, but were included in the historical broad sensitivity cohort. Both results must be retained. This is transfer beyond the primary cohort, with prior broad-sensitivity exposure and substantial complete-case selection.

An additional genuinely unexposed, measurement-compatible source would support a stronger evaluation. An individual-country download containing the same establishments is not a new sample. Another business function measured in the same firms tests internal generality. It is not independent external validation. No such additional source is silently substituted in this phase.

## Eligibility and the evaluation label

Use the exact archived source and establishment eligibility contract. The primary cohort has 14,412 eligible establishments in 12 sources. The broad eligible cohort has 14,818 establishments in 14 sources. Their archived membership digests must match before aggregation. The original CSV container and pooled member are pinned separately.

Each eligible establishment has positive sales `e6a`, positive workers `s7`, a positive sampling weight and exactly one binary MOST planning indicator among `ib9b1` to `ib9b5`. The outcome is `log(e6a/s7)`. Within each eligible source, retain the historical weighted 20th-percentile rule: stable ascending order, the first cumulative weight reaching 20% and all observations tied at the resulting threshold. Report realised weighted event prevalence. Do not force it to equal exactly 20%.

The event threshold is constructed within the test source using a locked definition. This uses test outcomes to define an evaluation label; it does not choose the technology coding or its priority order. The estimand is relative low performance within a source. It is not transport of an absolute monetary threshold.

Normalise the original positive weights to mean one within each eligible source. The quota concerns expected weighted contacts. It is not an exact number of firms, a budget or a realised list under one random draw.

Poland's interval-coded sales and employment are not replaced by arbitrary midpoints. Chile's 19 eligible records do not enter through a relaxed sample threshold. The low sales coverage of Burkina Faso and Cambodia remains a limit on their complete-case test populations, even if their numerical results appear favourable.

## Policy and training selection

Priority always follows states 1 to 5 in the instrument order. Contact all lower-priority-number blocks until capacity reaches the marginal block. Within a block every establishment has the same contact probability. A zero-mass state is represented explicitly and does not prevent filling the quota. Never reorder states by observed event risk.

Fixed policy cuts are `(1,2,3,4)` for five states, `(1)` for manual versus any digital technology and no cuts for a population lottery. The three-block candidate class is exactly `(1,2)`, `(1,3)`, `(1,4)`, `(2,3)`, `(2,4)` and `(3,4)`.

For each candidate and each quota, calculate the signed yield difference between the five-state policy and the candidate separately in every training source. Average that signed difference equally across training sources. Select the candidate with the smallest maximum of the four quota-specific means. On an exact tie, choose the lexicographically smallest cut pair. Keep one selected coding across all target quotas. Do not choose a new coding for each quota.

Negative yield losses remain negative. The five-state policy is a fixed benchmark with more recorded categories, not an oracle that is guaranteed to dominate in a source with a non-monotonic event gradient. The criterion has no tunable penalty or model hyperparameter. A redundant inner cross-validation stage is not added.

Fit and score use separate interfaces. A training lock records training source and country sets, candidate objectives, selected cuts, code digest, algorithm digest, protocol digest and input digest. Scoring rejects source overlap and can enforce country disjointness. A local lock binds content; it does not authenticate an empirical input or erase prior analyst exposure.

## Joint reporting

For each source, policy and quota retain expected weighted contacts and cases, cases per 100 contacts, realised event prevalence, event recall and the expected contact share of every original state. Report signed yield and state-share differences relative to both fixed digital and five-state allocation. Report the total variation distance of the five-state contact composition in percentage points. The latter measures redistribution, not whether the redistribution is desirable.

Source-transfer summaries give every source equal weight. Country-transfer summaries give every country equal weight and every source within its country equal weight. Secondary summaries pool expected weighted contacts, retaining continuity with the article's sample-size emphasis. These estimands are labelled separately. A mean source-level composition distance and the composition distance of a pooled list need not coincide.

All folds, both excluded-primary sources, every selected coding and all four quotas remain in the private result record. No favourable-source selection, alternative quota selection or post-test reinterpretation of the event is allowed. Any new analysis choice is a dated amendment and is identified as such.

## Verification and release

The source-cell engine uses exact rational arithmetic for allocation and selection. Verification includes hand-computable cases, a separately written row-based oracle, held-out-label perturbations, country exclusion, row-order invariance, empty states, non-monotonic event risks, exact selection ties, input/protocol/code mismatches and source-overlap refusal.

Synthetic fixtures test software. Recalculation from historical pooled aggregates tests agreement with the archived summaries. A run from the pinned original FAT input would be a new empirical execution. Neither synthetic results nor pooled reconciliation is labelled empirical source transfer.

Source cells alone do not support sampling confidence intervals, equivalence, noninferiority or claims of statistical significance. Survey-aware uncertainty would require row-level data and documented survey-design information. A few source strata or two low-coverage test sources do not establish international transportability.

The first-phase package is a private extension overlay. The F3 submission materials, mathematical proofs and exact author-approved AI declaration remain unchanged. Source-specific small cells and raw records are not automatically released. Integration into the manuscript follows verified empirical results and a further critical audit. External submission, publication, messaging, DOI actions and costs require the applicable authorisation. GitHub Actions remain excluded.
