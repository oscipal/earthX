# Gelistete Handeinträge

Gelistete Einträge, die Otto von Hand freigibt (`adr/0033` F11, M5-17), je eine Datei `<dataset_id>.yaml`. Nur
`catalog-load` liest sie und schreibt sie in die Tabelle `earthx_listed_entry`; kein Prozess lädt sie in die Registry
(`adr/0025` §7.1 in der Fassung von `adr/0033`). Die Felder sind die von `earthx.catalog.listed.ListedEntry`; der Merge
der Datei ist die Freigabe, `approved_on` ihr Tag. Wird eine Datei gelöscht, wird der Eintrag ein Grabstein mit Grund
`source_removed` (`api` antwortet `410`). Gesperrt wird über `../blocked.yaml`. Deckt das Rechteck eines
Eintrags mehr ab als die Daten, nennt `coverage_states` die abgedeckten Staaten (ISO 3166-1); Umriss und Regionen
kommen dann aus ihren Umrissen in `../regions.json`, beschnitten auf das Rechteck (M5-17 F4).
