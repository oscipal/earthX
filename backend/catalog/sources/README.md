# Quellen des Harvest

Je Quelle eine Datei `<source_id>.yaml` (`adr/0025` §5.2, Plan `docs/plans/m5/m5-19-harvest-kern.md` §4.1). Der Merge
einer Datei ist Ottos Freigabe der Quelle (`adr/0033` §4). Gelesen von `discovery`; die Registry liest nur die Hosts,
weil deren Grenzen in `../hosts.yaml` stehen. Die Felder prüft `earthx.catalog.sources`; die Quell-ID `listed` und das
Präfix `proto-` sind vergeben. `enabled: false` hält eine Quelle an, ohne die Datei zu löschen.

- `catalog_page`: Seite eines Datensatzes im Katalog mit `{id}` (STAC) bzw. `{name}` (CKAN), letzter Rang des Links
  „Source“ (Plan §6), oder `null`.
- `filter`: STAC `collection_prefixes` (leer = alle); CKAN `fq` wörtlich oder `null` und `publisher_field`
  (`publisher_name` bei DCAT-AP.de, `organization` sonst); `page_extras`: Schlüssel von `extras`, die nach `url` als
  Seite des Datensatzes gelesen werden (GovData `[uri, guid]`, F12 = 1).
- `max_requests_per_run`: Obergrenze, danach endet ein Lauf `interrupted`. `max_pages_per_run`: nur CKAN, `null` oder die
  Seiten eines Laufs; danach endet er `interrupted` (`page_budget`), und der nächste setzt fort (Otto, 18.11.2026).
  `rows_per_page`: nur CKAN, `null` (100) oder die Pakete je Seite (Otto, 19.11.2026). `full_every_days`: Abstand
  der vollen Läufe einer CKAN-Quelle; dazwischen fragt ein Lauf nur nach geänderten Paketen.

- `robots_exception`: `null` (`robots.txt` gilt streng) oder `path` (genau der Pfad von `endpoint` mit `/` am Ende,
  also nur die Metadaten-API) und `evidence` (`https`-Adresse der Doku, in der der Anbieter diese API zur Nutzung
  beschreibt). Hebt nur das `Disallow` für diesen Pfad auf; `Crawl-delay` gilt weiter (Otto, 18.11.2026,
  `adr/0025` §6.2).
- `country`: Staat (ISO 3166-1) der Datensätze des Katalogs oder `null` (Katalog der Welt); letzte Stufe der räumlichen
  Ausdehnung, nur als Region, ohne Fußabdruck (M5-20 Plan §6.1, F1 = 1).
- `dedupe_rank`: Vorrang unter Dubletten, 1 vor 2 (M5-20 Plan §8, F4 = 1): der Katalog des Anbieters vor dem Portal,
  das von ihm erntet.
- `dedupe_collection_links` (optional, Standard `false`): Eine Collection der FSDI, die ein Viewer-Link in den
  Dateien, den Kandidaten oder der übersprungenen Seite eines Fundes nennt (`map.geo.admin.ch` mit `layers=`,
  `data.geo.admin.ch` mit `/collections/<id>`), ist ein Dedupe-Schlüssel, wenn es genau eine bekannte ID ist
  (Otto, 24.11.2026; nur opendata-swiss).

Den Lauf beschreibt die README im Wurzelverzeichnis („Quellen ernten“).
