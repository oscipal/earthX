# Wechsel des lokalen Postgres auf PostGIS 3.7 mit pgvector (M5-43)

Einmalig für einen bestehenden lokalen Bestand. Ablauf und PowerShell-Befehle: `docs/plans/m5/m5-43-postgres-pgvector.md` §11.
Alle Dateien laufen im Container `postgres` (`docker compose cp`, dann `docker compose exec`).

| Datei | wofür |
|---|---|
| `versions.sql` | Fassungen von Postgres und Erweiterungen, Collation-Version je Datenbank, Größe |
| `counts.sql` | genaue Zeilenzahl je Tabelle, vorher und nachher zu vergleichen |
| `upgrade.sql` | `ALTER EXTENSION … UPDATE` für alle Erweiterungen, `REINDEX DATABASE`, Collation-Version auffrischen (eine Datenbank) |
| `upgrade-all.sh` | `upgrade.sql` in jeder Datenbank, die Verbindungen annimmt |
