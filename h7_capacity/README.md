# Reproduce the H7 capacity analysis

This proposed addition builds Table 5, Figure 3 and their numerical checks from the archived H7 aggregate results. It is staged as part of the planned 1.1.0 update. It does not change the immutable published v1.0.0 release, publish a new release or assign a DOI.

Use a separate Python 3.12 environment. The original analysis requirements alone are insufficient for the native ODG export, which also needs `lxml==6.1.1`. The supplied complete Linux/Python 3.12 lock contains the original 16 pins, their two recorded timezone dependencies and lxml. From the flat repository root (the wrapper locates this repository automatically):

```sh
python3.12 -m venv ../papere_h7_env
../papere_h7_env/bin/python -m pip install -r h7_capacity/requirements-complete-linux-py312.txt
../papere_h7_env/bin/python -m pip check
../papere_h7_env/bin/python h7_capacity/reproduce.py --output ../h7_capacity_output
```

When testing this folder as a separate overlay, identify the existing software tree explicitly:

```sh
/path/to/papere_h7_env/bin/python h7_capacity/reproduce.py --source-repository /path/to/software --output /path/to/new_output
```

The output directory must be new and outside both software folders. The command checks the pinned country and equal-country aggregate identities, runs the original independent synthetic checker, rebuilds the two capacity tables and all four Figure 3 formats, verifies the full six-policy menu at every quota and checks the expected CSV and PNG byte identities. No microdata is accessed, no models are fitted and no network connection is needed. The synthetic checks are not an empirical rerun.

The command records its environment, component exit codes and output hashes in `H7_REPRODUCTION_RECEIPT.json`. Individual logs and numerical reports remain available in the output directory. In a matching plotting environment, both derived CSVs and the PNG reproduce byte for byte. PDF, SVG and ODG metadata can include different creation times. SVG policy coordinates and endpoint segments are checked numerically. ODG checks cover archive structure, native paths, text equality with the SVG and the absence of embedded images or objects. The PDF check is limited to its header and a page marker; it does not establish visual or numerical equivalence. The supplied ODG contains native editable paths and text.

`H7_RAW_COST_SENSITIVITY.csv` keeps the raw capacity difference separate from the anchored sensitivity quantity. The hypothetical same-case cost threshold is the ratio of equal-country mean raw capacity gain to mean weighted query share. At the 50% logistic quota it is 4.2277373% for Full and 6.7438356% for Band 50%. The Band 50% anchored slope of 6.9741435% is a different quantity. Neither unit cost is observed. The acquisition menu omits SectorFixed, whose full-measurement allocation constraint is analysed separately; aggregate accounting still checks its rows.

The source input is `reported_results/H7/equal_country_policy_summaries.csv`, with SHA-256 `f3dcd98ad052d42281bf25ee8c992cf46abf213a48e8de5ccceda93fc4466f86`. `INTEGRATION_PROVENANCE.json` records the R2 supplement bundle and the unchanged builder, verifier and ODG-converter identities. The root `LICENSES.md` and `RIGHTS_AND_PROVENANCE_EN.md` remain authoritative; this addition does not grant permission to redistribute the FAT input.

Use the separate entry point above. The unchanged root `reproduce.py --mode all` runs the published analysis and excludes this additional capacity-derivative command. Run both commands when both kinds of reproduction are required. A successful capacity-derivative run is not evidence that a fresh raw-data engine run has succeeded.

The R4 wrapper supports both the earlier packaged layout and this flat repository layout, with automatic source-folder discovery and output containment. The capacity builder, mathematical verifier, aggregate checker, ODG converter and dependency files remain unchanged from the R3 addon. `--source-repository` still accepts a separate frozen software tree.
