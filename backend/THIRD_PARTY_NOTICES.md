# Fremddaten im Backend

Hinweise zu Daten Dritter, die mit dem Backend ausgeliefert werden. Die Python-Abhängigkeiten stehen mit ihrer Lizenz in
`requirements.lock` bzw. in ihrem Paket; Hinweise zum Frontend in `frontend/THIRD_PARTY_NOTICES.md`. Wo ein Paket eine
Bibliothek mitbringt, ihren Lizenztext aber nicht, liegt er unter `backend/licenses/` und im Image unter
`/app/licenses/` (Abschnitt „Bibliotheken ohne Lizenztext im Paket“).

## Natural Earth (Ländergrenzen 1:50m)

- **Wofür:** `catalog/places.json`, die Ländernamen (englisch und deutsch) und vereinfachten Umrisse, aus denen der
  Suchtext eines Datensatzes seine Ortsbegriffe ableitet (`docs/plans/m5/m5-22-suche-lexikalisch.md` F4).
- **Quelle:** Natural Earth, „Admin 0 – Countries“, Maßstab 1:50m, Release 5.1.2, Datei
  `geojson/ne_50m_admin_0_countries.geojson` aus dem Repository <https://github.com/nvkelso/natural-earth-vector>
  (SHA-256 in `catalog/places.json`). Reduziert mit `scripts/write-place-outlines.py`: nur Kennung, Name englisch und
  deutsch, Kontinent und Umriss, vereinfacht auf 0,1° und gerundet.
- **Lizenz:** Public Domain. Eine Nennung ist nicht verlangt; sie steht hier freiwillig.
  „Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.“

## IBM Granite Embedding 97M Multilingual R2 (Modell der Suche)

- **Wofür:** der Vektorarm der Datensatzsuche (M5-23, `adr/0026` F2; `docs/plans/m5/m5-23-vektorsuche.md`). Nur in der
  Image-Stufe `search` von `api` und `catalog-load`, nie im Repo und nie im Runner.
- **Quelle:** <https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2>, Revision
  `835ad14087e140460703cf0fae09f97d469d65c2`, Dateien `onnx/model.onnx` und `tokenizer.json` (SHA-256 in
  `backend/Dockerfile`, Stufe `model-files`). Die Vektoren in `backend/tests/fixtures/search/embeddings.json` sind mit
  diesem Modell gerechnet.
- **Lizenz:** Apache-2.0 laut Modellkarte (IBM). Einstufung als Vorschlag; Otto bestätigt Modell und Lizenz im PR
  (`adr/0026` F2, Plan F1).

## Natural Earth (Staaten 1:50m, Unterteilungen 1:10m)

- **Wofür:** `catalog/regions.json`, die Regionen gelisteter Einträge (`earthx:regions`, `adr/0033` §5): alle Staaten mit
  ISO-3166-1-Kennung und die Unterteilungen von Deutschland, Österreich, der Schweiz und Liechtenstein mit
  ISO-3166-2-Kennung (`docs/plans/m5/m5-40-gelistete-in-postgres.md` F8).
- **Quelle:** Natural Earth, „Admin 0 – Countries“ 1:50m und „Admin 1 – States, Provinces“ 1:10m, Release 5.1.2,
  Dateien `geojson/ne_50m_admin_0_countries.geojson` und `geojson/ne_10m_admin_1_states_provinces.geojson` aus dem
  Repository <https://github.com/nvkelso/natural-earth-vector> (SHA-256 in `catalog/regions.json`). Reduziert mit
  `scripts/write-region-outlines.py`: nur Kennung, Name, Ebene und Umriss, vereinfacht auf 0,02° bzw. 0,002° und
  gerundet.
- **Lizenz:** Public Domain; Einstufung durch Otto am 15.11.2026: Processing. Eine Nennung ist nicht verlangt; sie
  steht hier freiwillig. „Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.“

## swisstopo swissBOUNDARIES3D (Gemeinden)

- **Wofür:** `catalog/municipalities.json`, die Gemeinden der Schweiz mit Kanton und vereinfachtem Umriss, über die
  der Bericht des Harvest Ortstexte wie „Stadt Bern“ einer Gemeinde zuordnet (`docs/plans/m5/m5-20-freigabe-geernteter-eintraege.md`
  F9). Bis Otto das Skript auf eine lokale Kopie anwendet, enthält die Datei keine Gemeinde.
- **Quelle:** swisstopo, swissBOUNDARIES3D, Ebene der Hoheitsgebiete (GeoPackage, LV95); Release, Dateiname und SHA-256
  stehen in `catalog/municipalities.json`. Reduziert mit `scripts/write-municipality-outlines.py`: nur BFS-Nummer,
  Name, Kanton und Umriss in WGS84, vereinfacht auf 0,001° und gerundet.
- **Lizenz:** freie Nutzung mit Quellenangabe (opendata.swiss `terms_by`); Einstufung durch Otto am 19.11.2026.
  Quellenangabe: „© swisstopo“.

## Bibliotheken ohne Lizenztext im Paket

### libaec (mit `libsz`)

- **Wofür:** Entpacken nach CCSDS bzw. SZIP. Mitgeliefert als gebündelte Bibliothek in den Wheels von `h5py`
  (`h5py.libs/libaec-*.so.0.1.4`, M5-11) und `rasterio` (`rasterio.libs/libaec-*.so.0.1.7`); keines der beiden Wheels
  legt ihren Lizenztext bei.
- **Quelle:** <https://github.com/Deutsches-Klimarechenzentrum/libaec> (auch <https://gitlab.dkrz.de/dkrz-sw/libaec>),
  Text `LICENSE.txt` beim Tag `v1.1.4`, gelesen am 17.11.2026.
- **Lizenz:** BSD-2-Clause. Klausel 2 verlangt den Text bei jeder Weitergabe als Binärdatei; er liegt unverändert in
  `backend/licenses/libaec-LICENSE.txt` und im Image unter `/app/licenses/` (Otto, 17.11.2026).
