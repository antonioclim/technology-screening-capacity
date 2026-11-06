# Figurile curente Paper E

PDF-urile pentru încărcare sunt în `upload_pdf/`, vectorii editabili în `editable_svg/`, iar codul și cele opt CSV-uri permit refacerea tuturor celor șase figuri. Comanda portabilă este în README_EN.md. Figurile principale 1/2 sunt cele condiționale; figurile vechi 1/2 au devenit S2/S3. S1 păstrează analiza veche de transfer a codificării și populațiile ei distincte.

Pachetul este local și nu a fost publicat. El nu conferă o licență nouă asupra datelor terților. Microdatele, identificatorii individuali și vectorii de predicții nu sunt incluși. Codul nu folosește un model generativ de imagini și nu modifică demonstrații matematice. Metadatele reale ale aplicației de plotting sunt păstrate.

Figura S4 adaugă comparaţia retrospectivă de achiziţie a informaţiei şi alocare sectorială fixată. Sunt şase figuri curente şi opt CSV de intrare. Sursa `sources/plot_acquisition.py` foloseşte numai cele două CSV agregate din `inputs/acquisition/`. Layoutul portret al figurii S4 păstrează valorile H7 şi permite citirea în supliment; diagnosticul lat iniţial rămâne în provenienţă. Linia benzilor nu este o frontieră optimă.

Verificarea H8 păstrată este în `provenance/H8_ALL_SIX_REPLAY_QA.json` şi `provenance/H8_FIGURE_PAYLOAD_QA.json`. Recipisele H3/H5/H6 sunt păstrate ca istoric al baseline-ului cu cinci figuri. Verificarea opţională a randării foloseşte Poppler şi dependenţele din `provenance/requirements-checks.txt`; generarea figurilor foloseşte numai `requirements.txt`.

Corecţia H9, faza 2, foloseşte date UTC reale la noile exporturi 1/2/S4 şi este documentată în `provenance/H9_F2_FIGURE_UTC_QA.json`. Pixelii PDF, textul, dimensiunile şi geometria SVG concordă cu H8. Toate PNG-urile şi artwork-ul S1–S3 rămân identice byte. Nu s-au ajustat modele în această corecţie.
