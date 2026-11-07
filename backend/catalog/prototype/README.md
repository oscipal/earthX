# Prototyp-Einträge

Hier liegen Registry-Einträge von Quellen mit **unklarer Rechtslage**, nur für Ottos lokale Erprobung
(`docs/adr/0024-prototyp-quellen.md`). Noch ist keiner eingetragen.

- **Nie im Image:** Das `Dockerfile` kopiert nur `catalog/datasets/` und `catalog/retired.yaml`; `.dockerignore`
  schließt dieses Verzeichnis zusätzlich aus (R4).
- **Geladen nur**, wenn `EARTHX_PROTOTYPE_SOURCES` auf das Verzeichnis zeigt, `EARTHX_PROFILE=local` gesetzt ist und
  `CI` nicht gesetzt ist. Jede andere Einstellung mit gesetztem Pfad bricht den Start ab (R5). Der Runner liest es nie.
- **Jeder Eintrag** heißt `proto-<name>.yaml`, hat eine ID mit Präfix `proto-`, `legal_status: unclear` und einen Satz
  `legal_note`, was unklar ist (keine Rechtsmeinung, R3). `legal_status` setzt nur Otto (R1).
- **Nur Quellen ohne Konto, Schlüssel oder Umgehen einer Sperre**; ausdrücklich untersagte Nutzung bleibt draußen (R2).
- **CI und Cloud-Sitzungen** prüfen die Einträge ohne Netz (`backend/tests/catalog/test_registry_loading.py`); die
  Quellen ruft nur Otto lokal ab (R10).

Außer `*.yaml` und dieser Datei darf hier nichts liegen; der Lader bricht sonst ab.
