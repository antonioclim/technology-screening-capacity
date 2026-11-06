# Historical canonical exporter

The exporter and its eleven tests are preserved as the exact H1 implementation used for the canonical H2 run. Its three hash-pinned aggregate parity reference CSVs remain in the private archive. They are not included in this public candidate. The canonical exporter can use a separately available reference directory through `--aggregate-reference`; the full eleven-test fixture set belongs to the private canonical snapshot.

The current public raw-data command is `../run_transfer_from_raw.py`. It reconstructs eligibility and source-state summaries with the independent raw-row implementation, then uses the unchanged exact engine. It needs only the original pinned FAT archive and the supplied publication aggregates. It does not require or claim to repeat the private thirty-nine-reference comparison.
