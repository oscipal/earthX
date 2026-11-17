# Quellen des Harvest

Je Quelle eine Datei `<source_id>.yaml` (`adr/0025` §5.2, Plan `docs/plans/m5/m5-19-harvest-kern.md` §4.1). Der Merge
einer Datei ist Ottos Freigabe der Quelle (`adr/0033` §4). Gelesen von `discovery`; die Registry liest nur die Hosts,
weil deren Grenzen in `../hosts.yaml` stehen. Die Felder prüft `earthx.catalog.sources`; die Quell-ID `listed` und das
Präfix `proto-` sind vergeben. `enabled: false` hält eine Quelle an, ohne die Datei zu löschen.
