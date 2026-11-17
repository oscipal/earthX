# Quellen des Harvest

Je Quelle eine Datei `<source_id>.yaml` (`adr/0025` §5.2, Plan `docs/plans/m5/m5-19-harvest-kern.md` §4.1). Der Merge
einer Datei ist Ottos Freigabe der Quelle (`adr/0033` §4). Gelesen von `discovery`; die Registry liest nur die Hosts,
weil deren Grenzen in `../hosts.yaml` stehen. Die Felder prüft `earthx.catalog.sources`; die Quell-ID `listed` und das
Präfix `proto-` sind vergeben. `enabled: false` hält eine Quelle an, ohne die Datei zu löschen.

- `catalog_page`: Seite eines Datensatzes im Katalog mit `{id}` (STAC) bzw. `{name}` (CKAN), letzter Rang des Links
  „Source“ (Plan §6), oder `null`.
- `filter`: STAC `collection_prefixes` (leer = alle); CKAN `fq` wörtlich oder `null` und `publisher_field`
  (`publisher_name` bei DCAT-AP.de, `organization` sonst).
- `max_requests_per_run`: Obergrenze, danach endet ein Lauf `interrupted`. `full_every_days`: Abstand der vollen Läufe
  einer CKAN-Quelle; dazwischen fragt ein Lauf nur nach geänderten Paketen.

Den Lauf beschreibt die README im Wurzelverzeichnis („Quellen ernten“).
