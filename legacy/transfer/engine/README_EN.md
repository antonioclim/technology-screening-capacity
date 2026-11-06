# Source transfer engine

`holdout_engine.py` uses the Python standard library and exact rational arithmetic. It evaluates five-state, digital-boundary, population-lottery and training-selected three-block screening at expected weighted quotas of 20%, 35%, 50% and 75%. The primary quota is 50%. It preserves the original state order and uses equal contact probabilities throughout a marginal block. Yield and original five-state contact composition are reported together.

For each of the six contiguous three-block candidates, the selection criterion calculates the signed five-state-minus-candidate yield difference for each training source, averages equally over those sources at each quota and minimises the largest of the four means. Exact ties select the lexicographically smallest cut pair. No event-risk ranking, target outcomes or target composition enters fitting. One partition applies to every target quota.

The input header is exactly:

```text
source,state,n,n_cases,weight_mass,case_mass
```

Every source supplies all five states, including explicit zero cells. Weights must be positive on occupied cells and normalised to mean one within source, with relative tolerance 1e-8 on their sum. Counts and weighted event masses must agree on empty, zero-event and all-event support. Recall is undefined when a source has no events. This is recorded as `null`, while yield remains defined. Small cells are permitted for private computation; these outputs have no automatic permission for public release.

An accompanying JSON manifest must contain `input_sha256`, `evidence_type` (`synthetic` or `empirical`), `sources` (mapping each source to its reporting country), `provenance` and `prior_exposure`. These fields record declarations and byte identity. They do not authenticate the truth or lawful origin of a dataset. The canonical empirical route is the separate pinned-raw exporter. The CLI authenticates the supplied H1 protocol bytes; amendments require an explicit implementation revision and matching identity bindings. The [protocol projection record](../../../docs/PROTOCOL_PROJECTIONS.md) explains the current public metadata and preserved scientific specification.

Fit and score are separate commands. The training lock records training sources, countries, candidate objectives, selected cuts and input, engine, algorithm and protocol digests. Scoring rejects overlapping sources and changed locks, code or protocol. `--country-disjoint` also rejects overlapping reporting countries. A local hash records file identity; it does not establish independently time-stamped preregistration or erase previous pooled exposure.

```bash
python3 engine/holdout_engine.py fit --input TRAIN.csv --manifest TRAIN_MANIFEST.json --protocol protocol/H1_PROTOCOL.json --output /absolute/new_train_lock.json
python3 engine/holdout_engine.py score --input TARGET.csv --manifest TARGET_MANIFEST.json --protocol protocol/H1_PROTOCOL.json --lock /absolute/new_train_lock.json --country-disjoint --output /absolute/new_target_scores.json
python3 engine/holdout_engine.py crossvalidate --input PRIMARY.csv --manifest PRIMARY_MANIFEST.json --protocol protocol/H1_PROTOCOL.json --unit source --output /absolute/new_source_cv.json
python3 engine/holdout_engine.py crossvalidate --input PRIMARY.csv --manifest PRIMARY_MANIFEST.json --protocol protocol/H1_PROTOCOL.json --unit country --output /absolute/new_country_cv.json
```

Run these commands from `legacy/transfer/`. `TRAIN.csv`, `TARGET.csv` and their manifests denote separately prepared inputs, not supplied empirical fixtures. Output files must be new paths outside the repository. Source folds exclude one source. Country folds exclude every source with the same supplied reporting-country label, including both India sources in the canonical metadata. The primary source summary weights sources equally. The primary country summary weights countries equally and sources equally within country. The secondary pooled summary weights by expected contacts, which at a common quota equals weighting by source eligible weighted mass. Event recall uses event masses, not contact weights. Primary contact and event masses are means per transfer unit; pooled masses are totals. Pooled composition distance is calculated from pooled signed composition differences, whereas the primary distance averages source distances.

Each source row includes yield per 100 expected weighted contacts, realised weighted event prevalence, event recall, expected contact and event masses, five original-state contact shares, signed yield and composition differences against five-state and digital policies and total variation composition distance against five-state. A change in composition has no assigned welfare sign. Negative yield gaps are retained. The engine supplies no confidence intervals, equivalence claims or inference that cross-source transfer establishes prospective external validity.

Software checks:

```bash
python3 -m unittest discover -s engine -p 'test_*.py' -v
python3 engine/demo_synthetic.py --protocol protocol/H1_PROTOCOL.json --output /absolute/new_transfer_synthetic
```

The unit tests and `demo_synthetic.py` use artificial data only. The generic fit/score commands evaluate the inputs identified in their manifests. Their numerical results are not held-out empirical evidence. Full target-specific and fold outputs remain private pending provenance, statistical and disclosure review.
