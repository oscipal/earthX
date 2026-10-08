# Eigene Migrationen

Hier liegen die SQL-Migrationen, die EarthX **neben** pgstac braucht. pgstac bringt
sein eigenes Schema und seine eigene Migration mit (`pypgstac migrate`, in compose der
Dienst `pgstac-migrate`); was hier liegt, gehört uns.

**Was hier liegt:** `002_search_cache.sql` — der Anwendungs-Cache aus E4, angelegt in
**M1-06** für die föderierte Item-Suche. In M1-04 war das Verzeichnis leer, weil
Collections in pgstac liegen; die Nummerierung beginnt deshalb bei `002` (die `001`
war die Buchführungstabelle, bevor sie zum Läufer wanderte, siehe unten).

`006_jobs.sql` — die Warteschlange der Jobs aus M4-08a (`adr/0013` §5.1, §6.3):
`earthx_recipe`, `earthx_run`, `earthx_job` und die Zeile `earthx_job_limits` mit Deckel
und Grenze je Host. Die Tabellen gehören dem Modul `jobs`, das sie nur mit SQL
anfasst; sie liegen hier, weil `jobs` `catalog` nicht importieren darf und die
Buchführung des Läufers eine einzige sein soll. Jeder Fremdschlüssel ist
`RESTRICT` und hat einen Index.

`007_run_attachments.sql` — die Spalte `earthx_run.attachments` aus M4-11a: die
Begleitdateien eines Export-Jobs (`ATTRIBUTION.txt`, `citation.bib`, `aoi.geojson`), die
`api` baut und `jobs` ungelesen an den Lauf weitergibt.

Die Buchführungstabelle `earthx_migrations` gehört nicht hierher, sondern dem Läufer
(`earthx/catalog/schema.py`) und wird von ihm angelegt. Sonst müsste jedes
Migrationsverzeichnis sie erneut mitbringen.

## Regeln

- Dateiname `<nnn>_<name>.sql`, dreistellig und fortlaufend: `002_search_cache.sql`.
- Eine angewandte Migration wird **nie** geändert. Der Läufer merkt sich eine
  Prüfsumme und verweigert den Dienst, wenn die Datei sich danach noch bewegt hat —
  eine nachträgliche Änderung ließe Datenbanken stillschweigend auseinanderlaufen.
  Stattdessen eine neue Datei schreiben.
- Datei und Buchungszeile laufen in einer Transaktion. Eine halb angewandte Migration
  kann deshalb nicht als erledigt gelten.
