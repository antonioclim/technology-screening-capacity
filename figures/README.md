# Figure gallery

The six current figures are shown below as PNG previews, with editable SVG versions and the reported CSV inputs. The plotting command also writes PDF exports outside the repository. The manuscript and editorial artwork kit are distributed separately.

## Regenerate the figures

From the repository root:

```sh
python -B reproduce.py --mode figures --output /absolute/new_figures
```

Or from this directory:

```sh
python -B generate_all_figures.py --output /absolute/new_figures
```

Both commands require a new output directory outside the package. They read eight pinned CSV files and do not fit models or read microdata. `INPUT_IDENTITIES.json` records the input hashes. Export dates may differ between runs; plot content and geometry are checked separately from export metadata.

## Numbering

Main figures 1 and 2 report the conditional comparisons. S1 contains the original coding-transfer comparison. S2 and S3 are the original pooled yield and composition figures. S4 reports selective querying and sector-fixed allocation.

## Figure 1

![Figure 1: reported screening results](preview_png/Figure_1.png)

Incremental planning yield from adding five-state MOST to B at a 50% quota within each source. The primary results exclude the scored country from estimation, averaging the two India sources within country. Secondary targets are scored after training on all twelve primary sources and are displayed separately. Horizontal segments run from zero to the fixed logistic yield contrast; no confidence intervals are shown.

[Editable SVG](editable_svg/Figure_1.svg) · [CSV 1](inputs/main/Figure_1_primary.csv) · [CSV 2](inputs/main/Figure_1_secondary.csv)

<details>
<summary>Detailed figure description</summary>

At a separate 50% expected weighted quota in each source, dots show the increase or decrease in low-sales-per-worker case yield after adding most-used planning technology to the same firm-characteristic baseline. Bangladesh and Brazil have large positive increments; four primary countries have negative increments. Separate squares show Burkina Faso at −8.94 and Cambodia at +3.33 cases per 100 expected weighted contacts. Horizontal segments join each contrast to zero and are not uncertainty intervals.

</details>

## Figure 2

![Figure 2: reported screening results](preview_png/Figure_2.png)

Consequences of replacing MOST with MAX at a 50% quota within each source. Panel A reports the yield of B plus MAX minus B plus MOST, in cases per 100 expected weighted contacts. Panel B reports total variation between their sectoral shares of expected contacts, in percentage points. Both procedures use the same firms, baseline and quota. India averages source-level results, including the source-level composition distances. The distances do not measure overlap between realised contact lists.

[Editable SVG](editable_svg/Figure_2.svg) · [CSV 1](inputs/main/Figure_2_construct.csv)

<details>
<summary>Detailed figure description</summary>

Two aligned panels compare most-advanced adopted with most-used planning technology, holding the firm-characteristic baseline, eligible firms and 50% source quota fixed. Panel A shows country yield differences, with a large negative value in Brazil and both positive and negative values elsewhere. Panel B shows nonnegative total-variation distances in the sector shares of expected contacts. Country-average sector distance is 6.83 percentage points; India averages its two source distances.

</details>

## Figure S1

![Figure S1: reported screening results](preview_png/Figure_S1.png)

**Yield and contact composition across survey sources.**

Each source has a separate 50% expected weighted quota. Panels A and B use source-exclusion choices for the primary sources and the all-primary training choice for the two shaded target sources. Negative yield differences are losses. Panel C shows that the identical ordered rules in Burkina Faso yield 15.54 cases per 100 expected weighted contacts against 20.71 for the lottery; their equality at this quota occurs within the manual block. The figure is plotted in Python from the accompanying result table and contains no confidence intervals.

[Editable SVG](editable_svg/Figure_S1.svg) · [CSV 1](inputs/transfer/within_source_quota_50_percent.csv)

<details>
<summary>Detailed figure description</summary>

Three panels show the original retrospective coding-transfer comparison at a 50% expected weighted quota within each source. Yield and original-state composition differences are compared with five states. The two sources outside the primary cohort are shaded. In the original Burkina Faso sample of 162 establishments, the three ordered policies yield 15.54 against 20.71 for the lottery. In Cambodia’s sample of 244 establishments, the selected three-group yield is 24.41. This differs from the later adoption-matched conditional cohorts used in main Figures 1 and 2.

</details>

## Figure S2

![Figure S2: reported screening results](preview_png/Figure_S2.png)

**Expected yield at equal pooled weighted contact capacity.**

The upper panel reports cases per 100 expected weighted contacts. The lower panel reports additional cases per 100 eligible weighted establishments from retaining five states. The best binary is selected retrospectively at each quota. FAT denotes the Firm-level Adoption of Technology survey.

[Editable SVG](editable_svg/Figure_S2.svg) · [CSV 1](inputs/pooled/capacity_curves.csv)

<details>
<summary>Detailed figure description</summary>

Two panels show the original single pooled-quota comparison of technology-priority rules. At 50% pooled expected weighted coverage five states and digital yield 24.59 and 24.19 cases per 100 expected weighted contacts. The lower panel shows the additional case mass per 100 eligible weighted establishments relative to digital, integrated and the retrospective best binary.

</details>

## Figure S3

![Figure S3: reported screening results](preview_png/Figure_S3.png)

**Original-state composition at 50% pooled expected weighted coverage.**

Shares describe expected weighted contacts by original planning-technology state under each ordered coding. They are not individual realised-list overlap. ERP denotes enterprise resource planning.

[Editable SVG](editable_svg/Figure_S3.svg) · [CSV 1](inputs/pooled/list_composition.csv)

<details>
<summary>Detailed figure description</summary>

Four stacked bars and a numerical table report original planning-state shares of expected weighted contacts at 50% pooled coverage. Five-state and digital rules both allocate 68.13% to manual planners. Digital coding moves 7.39 percentage points from standard software to the three more advanced states. Other bars show integrated-boundary and lottery compositions. These are expected distributions, not realised-list overlap.

</details>

## Figure S4

![Figure S4: reported screening results](preview_png/Figure_S4.png)

Technology acquisition and sector-fixed allocation at a 50% expected weighted contact quota within each source. Panel (a) reports equal-country mean yield increments over B against the actual weighted query coverage of the prespecified acquisition bands, for the logistic procedure and fixed depth-3 tree. Stars mark bands selected using only training-country nested validation. Lines connect the prespecified diagnostic bands and do not represent an optimal frontier. Whole score ties can expand actual query coverage. Panel (b) compares country-specific logistic increments over B with full technology ranking and with each sector held at its B expected contact mass. Both India sources are averaged within country before the eleven-country mean. The points are descriptive estimates without confidence intervals.

[Editable SVG](editable_svg/Figure_S4.svg) · [CSV 1](inputs/acquisition/country_sector_fixed.csv) · [CSV 2](inputs/acquisition/mean_acquisition.csv)

<details>
<summary>Detailed figure description</summary>

Two vertically stacked panels show retrospective comparisons at a 50% contact quota. In panel (a), the selected logistic policy queries 84.63% of eligible weighted mass and adds 1.07 cases per 100 expected weighted contacts, compared with 1.77 for full acquisition; the selected fixed tree queries 63.78% and adds 1.22, compared with 1.89 for full acquisition. Panel (b) shows all eleven countries for the logistic comparison. Holding sector contact mass fixed retains a mean increment of 0.89 cases per 100 contacts, positive in eight countries and negative in three. These are descriptive estimates, not confidence intervals or a guarantee of performance.

</details>

## Plotting source

`sources/plot_main_figures.py` produces figures 1 and 2; `sources/plot_supplement_transfer.py` produces S1; `sources/plot_pooled.py` produces S2 and S3; `sources/plot_acquisition.py` produces S4. `generate_all_figures.py` coordinates those sources and writes receipts. Historical diagnostic plotting source is retained under `sources/historical/`; it is not an additional numbered article figure.
