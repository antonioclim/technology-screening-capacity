# Paper E current figure package

These are the six figures for *Which Firms Make the List? Technology Measurement under Fixed Screening Capacity* by Antonio Clim. The numerical content and layouts of the five canonical H5/H6 figures are retained. H9 regenerates Figures 1 and 2 with genuine UTC export dates; Figures S1–S3 remain byte-identical. Figure S4 adds the H7 acquisition and constrained-allocation comparison in a portrait layout for print legibility; the numerical data are unchanged. Figures 1 and 2 report conditional screening comparisons; the earlier pooled figures are now Figures S2 and S3. Figure S1 remains the original source-transfer coding exercise. Captions and alt text use the current numbering.

## Rebuild from aggregate CSVs

Use Python 3.12.14 with `requirements.txt` installed in the selected environment:

```sh
python generate_all_figures.py --output /absolute/path/to/new_figure_output
```

The output path must not exist and must lie outside this reference figure package. The command also works from another working directory when the script is given by its absolute path. It reads the eight pinned CSVs under `inputs/` and creates current-numbered PDFs, editable SVGs and PNGs in separate `pdf`, `svg` and `png` folders. Logs, input identities and output hashes distinguish figure generation from empirical re-execution. No raw data, model fitting or network access is required. The code does not select a learner or change scientific results.

The main plotting source, with an explicit UTC export-date correction, is in `sources/plot_main_figures.py`, the pooled source in `sources/plot_pooled.py` and the current Supplement S1 source in `sources/plot_supplement_transfer.py`. The historical CSV wrapper is preserved at `sources/plot_transfer.py`; the earlier private-result formatting helper remains under `sources/historical/`. They are not additional current figures. The wrapper maps historical pooled export stems to S2 and S3 without overwriting main 1 and 2.

CSV inputs are source/country or pooled aggregates, not establishment records. Their local inclusion supports review and reproducibility; this package is prepared locally and is not a public deposit, a new data licence or approval to redistribute third-party data. The provider’s access and reuse conditions remain applicable. No software DOI is invented. The exact approved AI declaration is included separately, and genuine Matplotlib software provenance remains in the artwork. No generative-image model was used.

Reference execution is Linux/Python. Native Windows or journal-portal execution is not claimed. PDF/SVG date fields and generated internal identifiers may differ between faithful reruns; numerical inputs, visible content, geometry and image comparisons are recorded separately.

Figure S4 uses `sources/plot_acquisition.py` and the two pinned CSVs under `inputs/acquisition/`. It reads no result directory, microdata or fitted models. Its original wide H7 diagnostic/source is retained under `provenance/` and `sources/historical/`; these historical files are not additional article figures. The current Figure S4 PDF, SVG and PNG share the portrait layout used in the supplement. The plot path is prespecified, not an estimated efficient frontier.

Retained H8 validation is in `provenance/H8_ALL_SIX_REPLAY_QA.json` and `provenance/H8_FIGURE_PAYLOAD_QA.json`. Earlier H3/H5/H6 receipts are preserved as historical evidence of the five-figure baseline. Optional comparison checks use `provenance/verify_all_six_figures.py`, `provenance/requirements-checks.txt` and the external Poppler `pdftoppm` command; the plotting entry point itself needs only `requirements.txt`. Comparison normalisation is in memory only and does not alter delivered metadata.

H9 phase2 UTC-export checks are recorded in `provenance/H9_F2_FIGURE_UTC_QA.json`. Figures 1, 2 and S4 were plotted again from unchanged CSVs; their PDF pixels, text and dimensions and SVG geometry match H8. All PNGs and S1–S3 artwork retain their earlier bytes. No model was fitted in this correction.
