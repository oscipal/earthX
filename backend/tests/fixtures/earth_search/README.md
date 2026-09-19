# Synthetische Earth-Search-Antworten

Diese Dateien sind **von Hand geschrieben**, nicht aufgezeichnet. Sie bilden die
Formen nach, die `docs/adr/0005-foederierte-item-suche.md` §3 an der echten Quelle
gemessen hat — Antwortrumpf mit `numberMatched`/`context`, `next`-Link als POST-Link
**mit Rumpf**, die Fehlerformen aus §3.5 —, enthalten aber keine echten Metadaten:
IDs, Zeiten, Geometrien und Asset-Adressen sind erfunden und klein gehalten.

**Warum synthetisch:** Die Lizenzlage der Earth-Search-Metadaten ist offen
(`adr/0005` §8 Punkt 1; `docs/plans/m1-06-earth-search-adapter.md` §9 F6). Solange sie
offen ist, kommt nichts Aufgezeichnetes ins Repo — `ENTSCHEIDUNGEN_2026-09-18.md` §4
lässt Fixtures nur synthetisch oder eindeutig offen lizenziert zu.

**Was sie deshalb nicht können:** belegen, dass die Quelle noch so antwortet. Genau
dafür gibt es den zeitgesteuerten Live-Smoke-Test (`backend/tests_live/`, T-D laut
`adr/0002` §2).
