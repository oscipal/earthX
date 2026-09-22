# Synthetische EOPF-STAC-Antworten

Von Hand geschrieben, nicht aufgezeichnet — dieselbe Regel wie bei
`tests/fixtures/earth_search/` (`ENTSCHEIDUNGEN_2026-09-18.md` §4,
`KLAERUNGEN.md` B2). Diese Dateien bilden die Formen nach, die die M2-09b
Plan-Sitzung an `stac.core.eopf.eodc.eu` gemessen hat: STAC-1.1-Items (`bands`
am Asset, `proj:code` statt `proj:epsg`, `raster:spatial_resolution` direkt am
Asset), **kein** `numberMatched`/`context` in jeder Suchantwort, der
Seiten-Link als POST-Link mit Rumpf, dessen Feld `token` heißt (nicht `next`
wie bei Earth Search). IDs, Zeiten, Geometrien und Asset-Adressen sind
erfunden und klein gehalten.

Belegt keine Quellenantwort von heute — dafür gibt es keinen Live-Smoke für
diesen Adapter (`adr/0002` T-D: `gateway` erreicht die Quelle aus einer
Cloud-Sitzung nicht, siehe `plans/m2-09b-zweiter-datensatz-katalog.md` §10 F7).
