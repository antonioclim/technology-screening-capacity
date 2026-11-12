# Changelog

## 1.1.0 — staged, not released

- Add the separate `h7_capacity/reproduce.py` command for Table 5, Figure 3 and numerical checks from pinned aggregate results. It performs no new model fitting and reads no microdata.
- Include all seven native editable ODG figures, their canonical vector PDF exports and the previously separate Figure 3 SVG/PNG. Provide the exact DejaVu Sans fonts used for the native drawings, with their existing licence notice.
- Update the figure gallery, captions, descriptions and numbering for three main figures and four supplementary figures.
- Record current preparation status, validation and file identities without assigning a new DOI or release date.

The existing root-level analysis commands, numerical source files, protocols, aggregate inputs and six original SVG/PNG figures remain unchanged. No baseline directory is moved or removed. `reproduce.py --mode all` retains its previous workflow; the capacity derivative remains a separate command using archived aggregates.

The new version has not been published. The immutable v1.0.0 release remains identified by DOI [10.5281/zenodo.24000396](https://doi.org/10.5281/zenodo.24000396) and commit `1ce158cb5c076de75257343ca5899c558849c518`. That DOI does not identify these additions. No licence grant has been silently broadened to FAT microdata or source-controlled data.

## 1.0.0 — 6 November 2026

Original public analysis software, protocols, reported aggregate tables, six figure sources and reproduction entry point. Historical packaging statuses in retained component documents refer to their preparation date; they are not the status of the staged 1.1.0 tree.
