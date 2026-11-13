# Licences and provenance

## Component licences

Antonio Clim's original source code, tests and operational software configuration are licensed under the [MIT License](LICENSE). His original documentation, public protocol documentation and original figures are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The [component licence map](LICENSES.md) defines these scopes and the boundaries for supplied aggregate tables.

Inherited notices are retained unchanged in [legacy_licences](legacy/transfer/extractor/vendor/provenance/legacy_licences/). Their historical titles and paths describe the material they originally accompanied. They do not replace the current repository map. Preserve applicable component notices and third-party exceptions when reusing or redistributing material. Dependencies remain subject to their respective upstream licences.

## Data source

The World Bank FAT dataset is acquired separately and is not relicensed. Its citation and access conditions remain applicable. The repository contains reported statistical aggregates and plotting inputs; it does not distribute raw FAT records or the original private exports. Existing content grants and applicable source conditions remain in force for supplied aggregate tables. See [DATA_BOUNDARY_EN.md](DATA_BOUNDARY_EN.md).

The [World Bank Microdata Library terms](https://microdata.worldbank.org/index.php/terms-of-use) provide for statistical and scientific research and reporting aggregated information. This does not grant permission to redistribute the supplied microdata, identify establishments or treat the underlying data as author-owned material.

## Repository provenance

Version 1.1.0 preserves the existing flat repository layout. It adds the H7 capacity derivative and the seven native editable figure sources, canonical vector PDFs and associated documentation. The existing numerical analysis, protocols, aggregate inputs, root reproduction command and dependency files remain unchanged. `SOURCE_INVENTORY.json` records the per-file comparison with public v1.0.0; `SHA256SUMS.txt` records the file identities in this package. No baseline file is moved or deleted.

The public v1.0.0 baseline derives from the reviewed R1 repository preparation and the H9 scientific software baseline. Its immutable commit is `1ce158cb5c076de75257343ca5899c558849c518`. Public protocol projections and historical locks retain their original scope; see [protocol provenance](docs/PROTOCOL_PROJECTIONS.md). The H7 derivative provenance is recorded in `h7_capacity/INTEGRATION_PROVENANCE.json`. The additional native-figure provenance is recorded in `figures/NATIVE_FIGURE_PROVENANCE.json`.

Matplotlib creator information and genuine export metadata are retained. The seven ODG files contain individually editable native paths and text. They are drawings, not charts linked to live data. The DejaVu Sans font files carry their own retained licence. Scientific plotting and native edit/save/reopen checks do not amount to a manual graphical-interface test on every platform.

The previous version DOI [10.5281/zenodo.24000396](https://doi.org/10.5281/zenodo.24000396) identifies v1.0.0 only. Version 1.1.0 uses DOI [10.5281/zenodo.24186153](https://doi.org/10.5281/zenodo.24186153). The author confirmed that this DOI was reserved in a saved Zenodo draft on 13 November 2026; `RELEASE_STATE.json` records the publication status at packaging. No actual release date is asserted in this package. The component licence grants above remain unchanged; the additions do not relicense FAT microdata or source-controlled data.
