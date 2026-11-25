# Kandidaten des vollen Wegs

Je Quelle ein Ordner `<quelle>/` mit zwei Dateien je Kandidat, geschrieben von `discovery propose` im Harvest-Lauf
(`scripts/harvest-cycle.ps1`, Plan `docs/plans/m5/m5-20-freigabe-geernteter-eintraege.md` §14.1):

- `<gelistete ID>.yaml`: was geerntet wurde, die vorgeschlagene ID des vollen Eintrags (`proposed_id`), wie er die
  gelistete Zeile ablöst (`takeover`: `coll`, `also_listed_as` oder `doi`), die Lizenz mit Stufe und Entscheidung
  nach Regeln (`legal_status: cleared`, `decided_by: rules`), das Ergebnis von Verify und leere Felder für das
  Onboarding (`way`, `profile`, `notes`).
- `<gelistete ID>.probe.json`: die normalisierte Collection, 1–3 Items einer STAC-Quelle und Verify, höchstens 50 KB,
  nur Metadaten (`adr/0031` §4.4).

Kandidat wird ein sichtbarer gelisteter Eintrag mit Raster in COG/GeoTIFF, NetCDF/HDF5 oder Zarr, mit einer Lizenz der
Stufe über `catalog` (Klassen K1 und K2, Otto 25.11.2026), einem Schlüssel zur Ablösung und bestandenem Verify ohne
Konto; höchstens 20 je Quelle und Lauf. Unveränderte Kandidaten werden nicht neu geschrieben, keine Datei wird
gelöscht; ist die gelistete Zeile nicht mehr sichtbar, steht ihr Zustand in `listed_state`.

Herausnehmen: den Eintrag in `backend/catalog/blocked.yaml` sperren. Nichts hier kommt ins Image
(`backend/.dockerignore`); den vollen Eintrag schreibt das Onboarding (`adr/0031`) in `backend/catalog/datasets/`.
