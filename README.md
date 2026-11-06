# Technology measurement under fixed screening capacity

Analysis software accompanying *Which Firms Make the List? Technology Measurement under Fixed Screening Capacity* by Antonio Clim. This is the H9 local release candidate. Editorial, documentation and UTC-export corrections preserve the empirical procedures and results. No public software release is implied by this local label. It combines the pooled coarsening and source-transfer calculations, conditional screening evaluation, same-firm function/model follow-up and the H7 constrained-allocation/acquisition extension. No new public repository release, deposit or software DOI is asserted. See `LOCAL_RELEASE_STATE.json` and `RIGHTS_AND_PROVENANCE_EN.md` for the actual status.

The software can reconstruct the empirical analyses from the original World Bank FAT ZIP obtained separately under the provider's conditions. It does not require the four private archived X04/X06/X07/X10 exports. Those exports, raw records, private source-state/group results, fit locks and row-level predictions are not distributed in this candidate. Empirical commands generate private analytical outputs outside this package. Their local generation does not authorise redistribution.

## Run the current entry point

Use Python 3.12.14 and install the pinned requirements in a suitable environment. The documented execution is Linux/Python. Native Windows execution has not been tested.

```sh
python -m pip install -r requirements.txt
python reproduce.py --mode synthetic --output /absolute/new_synthetic
python reproduce.py --mode figures --output /absolute/new_figures
python reproduce.py --mode prepare --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_preparation
python reproduce.py --mode acquisition --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_acquisition
python reproduce.py --mode all --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_complete_run
```

Every output directory must be new and outside the payload. Absolute input/output paths can use the operating system's own path syntax; this does not claim a native Windows execution. Commands do not contact external services, download data, publish results or run GitHub Actions.

| Mode | Calculation | Empirical status |
|---|---|---|
| `synthetic` | Declared legacy, conditional, follow-up and acquisition software fixtures (56 tests) | No empirical data read |
| `figures` | All six current numbered figures from supplied aggregate CSVs | Plot generation only |
| `prepare` | Raw input authentication and H4/H5 cohort construction | No fitted screening scores |
| `pooled` | Original pooled quota curves and deletion bounds | Raw empirical reconstruction |
| `transfer` | Retrospective three-group coding transfer | Raw empirical reconstruction |
| `conditional` | H4 six-cohort, sixteen-policy evaluation and accounting | Raw empirical rerun |
| `followup` | H5 same-firm function and fixed-tree evaluation and accounting | Raw empirical rerun |
| `acquisition` | H7 sector-fixed allocation, nested query selection, random comparator and ex-post capacity diagnostics | Raw empirical rerun |
| `all` | All canonical empirical engines, declared fixtures and current figures | Combined native rerun |

The wrapper records each subprocess and its exit status. A failed stage leaves a FAILED receipt; it is not reported as complete. Mode receipts do not provide survey confidence intervals, formal verification or a prospective sample.

## Data identity and distinct comparisons

The external input is `WLD_2019-2023_FAT_v01_M_CSV.zip`, SHA-256 `6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e`. Each raw-data engine separately checks its required input/member/software identities. Dataset DOI: https://doi.org/10.48529/assd-3j65 . This is the World Bank dataset DOI, not a software DOI.

The original pooled coarsening comparison uses 14,412 establishments and one quota across that pooled population. Coding transfer fills each source's quota separately. H4 uses 13,996 matched planning establishments for its primary conditional comparison; the H5 direct function comparison uses 13,617 common establishments and preserves the original planning event labels. These are distinct analytical populations and allocation contracts. Burkina Faso and Cambodia remain separate secondary targets, with the corresponding sample restrictions reported in the article.

The productivity case definition is source-relative sales per worker at or below the inclusive weighted twentieth percentile, anchored before adoption matching. B contains sector, start year, multi-establishment status and foreign ownership. Country exclusion removes both India sources together. Evaluation uses within-source mean-one survey weights. Training gives countries equal total weight and India sources equal weight, then rescales fitting weights to the training sample size. Numeric transforms are learned only on training data. Exact score ties receive a common fractional probability that fills the expected weighted quota.

H4 fixed logistic regression remains the primary procedure. H5 is a retrospective follow-up chosen after H4, with a fixed depth-three tree and no hyperparameter selection. Function and learner results do not replace the H4 hierarchy. The finance objective is reported unmet borrowing for production expansion over a retrospective three-year window; it is not technology-specific finance, creditworthiness or the benefit of a programme.

## Source layout and current figure numbers

`legacy/` preserves original pooled, deletion and coding-transfer implementations and their reported aggregate inputs. Its original README and figure filenames describe that historical analysis: old Figure1 is now FigureS2, and old Figure2 is now FigureS3. These historical names are provenance and are not the current main artwork numbering. `conditional/` is the H4 engine. `followup/` is the H5 engine. `acquisition/` is the H7 extension. `figures/` supplies the current numbered Figure1, Figure2 and FiguresS1–S4 with CSV inputs and plotting applications. `SOURCE_INVENTORY.json` identifies every copied source and whether its bytes are unchanged.

`document_checks/` retains checking source used in the private document audit. It expects the documented private document/reference layout and is not part of a public empirical reproduction claim. Independent empirical calculation commands and their exact scopes are in `INDEPENDENT_CHECKS_EN.md`.

The scripts retain all declared adverse results. The positive mean planning increment does not establish transportability: country signs differ and the Burkina Faso/Cambodia increments change sign between the fixed logistic and tree procedures. Expected-contact distances do not identify overlap of realised lists, causal programme gains, welfare or money saved. Overlapping country folds are not independent replications.

## Constrained allocation and selective querying

The H7 extension keeps the 13,996-firm primary planning cohort, its original event labels, the fixed logistic primary model and the depth-three tree sensitivity. It holds each sector at its B expected contact mass, tests query bands selected only within training-country exclusions and computes a retrospective baseline-capacity inverse. Acquisition preserves B contact probabilities outside the queried pool. Whole B-score ties are queried; nominal bands may therefore query substantially more weighted mass or more firms than their nominal width.

All band choices and both learners are retained. At 50%, the training-selected logistic rule queries a mean 84.634% of weighted eligible mass and loses 0.707 cases per 100 expected weighted contacts relative to full technology information. The sector-fixed logistic increment is 0.893. These descriptive results do not identify monetary savings, programme benefits or a generally transferable acquisition rule. The capacity inverse explicitly uses held-out outcomes after evaluation; it is not an operational quota estimator. Random masks match expected weighted query mass, not respondent count or interview cost. Monte Carlo errors concern algorithmic randomisation only.

`reported_results/H7/` contains four country/equal-country aggregate tables. The source, group, fit and random-replicate outputs are generated privately by a rerun and are excluded from the static software tree. The author retains the full original H7 receipts and the earlier reporting-count correction in the private continuity archive. H7 is retrospective and does not create an unexposed external sample.

## Use of AI-assisted tools

ChatGPT and Codex (OpenAI) assisted with English-language drafting and revision, bibliographic checks, code debugging and document checks. Figures 1 and 2 were plotted from the result tables using Python. No generative-image model was used for either figure. I reviewed and edited the resulting material as needed and take full responsibility for the published article.
