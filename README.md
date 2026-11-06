# Technology measurement under fixed screening capacity

Analysis software accompanying **Which Firms Make the List? Technology Measurement under Fixed Screening Capacity**, by Antonio Clim.

This repository contains the screening calculations, protocols, reported aggregate results and Python plotting applications. The manuscript and submission documents are distributed separately.

## Start here

| Task | Entry point | Input |
|---|---|---|
| Run the five synthetic test suites | `reproduce.py --mode synthetic` | Supplied fixtures |
| Regenerate all six figures | `reproduce.py --mode figures` | Eight supplied aggregate CSV files |
| Prepare the analytical cohorts | `reproduce.py --mode prepare` | Original FAT ZIP, obtained separately |
| Rerun an empirical analysis | `pooled`, `transfer`, `conditional`, `followup` or `acquisition` mode | Original FAT ZIP |
| Run the combined workflow | `reproduce.py --mode all` | Original FAT ZIP and supplied figure CSV files |

See the [figure gallery](figures/README.md), [data boundary](DATA_BOUNDARY_EN.md), [independent checks](INDEPENDENT_CHECKS_EN.md), [local validation](docs/VALIDATION.md) and [licences and provenance](RIGHTS_AND_PROVENANCE_EN.md).

## Environment and commands

The documented environment is Python 3.12.14 on Linux. Install the pinned packages from the repository root:

```sh
python -m pip install -r requirements.txt
python -B reproduce.py --mode synthetic --output /absolute/new_synthetic
python -B reproduce.py --mode figures --output /absolute/new_figures
```

Every output directory must be new and outside the repository. The absolute paths above are examples: replace them with paths for your machine. Native Windows execution has not been tested.

For empirical work, obtain `WLD_2019-2023_FAT_v01_M_CSV.zip` through the [World Bank Microdata Library](https://microdata.worldbank.org/catalog/8209). Then run:

```sh
python -B reproduce.py --mode prepare --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_preparation
python -B reproduce.py --mode acquisition --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_acquisition
python -B reproduce.py --mode all --microdata /absolute/WLD_2019-2023_FAT_v01_M_CSV.zip --output /absolute/new_complete_run
```

The other empirical modes select one analysis rather than the combined workflow. Each command records subprocesses, exit codes and local logs. A failed stage leaves a failure receipt. The `all` workflow regenerates figures from the supplied reference CSV files; it does not automatically substitute newly fitted results into the figure inputs. Compare new analytical outputs with the archived tables before using them to make figures.

No command downloads data, contacts an external service or publishes results. Generated detailed analytical outputs belong outside the repository. GitHub Actions are not used.

## Data and analytical comparisons

The source dataset is *Technology Sophistication Across Establishments 2019–2023*, release `WLD_2019-2023_FAT_v01_M`, DOI [10.48529/assd-3j65](https://doi.org/10.48529/assd-3j65). The required ZIP has SHA-256:

```text
6d77d3ffb9dcef2ca4534e1c438ddd2e0b357eb852e6c5b48aa5fa6c3cbe2f0e
```

This is the dataset DOI, not a DOI for this software. The reader checks the input identity before empirical execution. The current raw-data routes do not require the four private historical X04/X06/X07/X10 exports.

The primary conditional comparison uses 13,996 establishments in 12 sources across 11 countries. A case has sales per worker at or below the source-specific weighted twentieth percentile, anchored before adoption matching. B contains sector, start year, multi-establishment status and foreign ownership. Country exclusion removes both India sources together. Training weights balance countries and the India sources, then sum to the training sample size. Numeric transformations are fitted on training data only. Score ties receive fractional contact probabilities that fill each source's expected weighted quota.

At the 50% source quota, adding most-used planning technology to the fixed logistic baseline increases equal-country mean yield from 23.44 to 25.21 cases per 100 expected weighted contacts. Holding each sector at its baseline contact mass retains an increment of 0.89. Country signs differ; these comparisons do not estimate intervention effects, monetary savings or prospective performance. The fixed shallow tree remains a sensitivity analysis. Selective querying retains its mean loss relative to full information.

The original pooled comparison uses 14,412 establishments and a single pooled quota. The matched planning–administration comparison uses 13,617 establishments. These populations and allocation contracts must be interpreted separately. The finance objective is reported unmet borrowing for production expansion over the previous three years.

## Repository map

| Directory | Contents |
|---|---|
| `legacy/` | Original pooled coarsening, deletion and coding-transfer calculations |
| `conditional/` | Fixed-logistic conditional screening evaluation |
| `followup/` | Same-firm function comparison and fixed-tree follow-up |
| `acquisition/` | Sector-fixed allocation, selective querying and capacity diagnostics |
| `reported_results/` | Reported country or equal-country aggregate tables |
| `figures/` | Gallery, eight CSV inputs, six SVG/PNG references and plotting source |
| `docs/` | Protocol projection and repository documentation |

The public protocol copies retain the scientific specifications. Administrative publication text has been separated from those specifications; [protocol provenance](docs/PROTOCOL_PROJECTIONS.md) records the resulting identity changes. Historical locks remain historical evidence and are not reassigned to this repository revision.

## What each workflow establishes

Synthetic tests check software behaviour on fixtures. Figure generation reconstructs plots from reported tables. Empirical reproduction requires the separately obtained original data. Independent calculations use the same dataset and do not constitute external validation. The retrospective design, sample selection and source-relative outcome limit transferability.

## Citation and rights

Author and repository information are in [CITATION.cff](CITATION.cff). A software DOI will be added once its actual deposit identity is available. Component notices and data-source conditions are described in [RIGHTS_AND_PROVENANCE_EN.md](RIGHTS_AND_PROVENANCE_EN.md).
