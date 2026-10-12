# M4-26 — Gleitkomma beim Schreiben einer Ganzzahl-Ausgabe runden statt abschneiden

**Stand:** 12.10.2026, beauftragt von Otto.
**Stufe A.** Direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** Nach M4-21. Die Aufgabe läuft neben Stufe-B-Sessions; Frontend wird nicht berührt.
**Startsatz:** „Führe Aufgabe M4-26 aus `docs/plans/m4-26-runden-ganzzahl.md` aus.“

## 1. Anlass

Aus M4-13b, Frage der Session vom 12.10.2026: Wählt der Nutzer eine Ganzzahl als Ausgabe (zum Beispiel `uint16` nach `bilinear`), schneidet der Kern Kommazahlen beim Schreiben ab. Aus 1234,7 wird 1234. Das verschiebt die Werte im Mittel um ein halbes Bit nach unten.

**Entscheidung Otto (12.10.2026):** runden statt abschneiden. Ein festes nodata je Typ für Quellen ohne nodata kommt vorerst nicht; dafür gibt es eine eigene Log-Zeile mit Status „offen“.

## 2. Umfang

1. **Stand der Technik mit Quellen.** Wie rundet GDAL beim Umwandeln von Gleitkomma in Ganzzahl (`GDALCopyWords`, `gdalwarp`, `gdal_translate -ot`)?
   - Wie wird bei x,5 gerundet: weg von null oder zur geraden Zahl?
   - Was passiert mit Werten außerhalb des Wertebereichs (Klemmen)?
   - Was passiert mit NaN?

   Aus der Session nicht erreichbare Seiten werden am Quelltext der Doku auf GitHub gelesen.
2. **Kern.** An der einen Stelle, an der der Kern in den Ausgabetyp umwandelt, wird nach der Regel aus Punkt 1 gerundet und auf den Wertebereich geklemmt. NaN bleibt nodata. Gibt es mehr als eine Stelle (Kern, Export, Mosaik), werden alle auf dieselbe Funktion umgestellt.
3. **Version.** Dasselbe Rezept liefert danach ein anderes Ergebnis.
   - Im PR zeigen, welche Version das abdeckt (`earthx.__version__` im Cache-Schlüssel wie bei K5 aus M4-12, `adr/0014` §4.3).
   - Passt keine bestehende Version sauber, dann Frage an Otto mit Optionen, bevor Code entsteht.
4. **Nichts sonst.** Keine Änderung an den Operatoren, an den Typregeln des Panels und an nodata.

## 3. Tests

- Gleitkomma-Werte wie 1234,4, 1234,5, 1234,6 und −0,5 sowie Werte über und unter dem Wertebereich, je für `uint8`, `uint16` und `int16`: Das Ergebnis folgt der belegten Regel.
- NaN wird zu nodata. Kein gültiges Pixel trifft nach dem Klemmen zufällig den nodata-Wert; falls doch, wird das wie bisher behandelt und im PR genannt.
- Gegenprobe: Mit Abschneiden scheitern die neuen Tests.
- Bestehende feste Hashes bzw. Bytes von Gleitkomma-Ausgaben bleiben unverändert.

## 4. Doku

- `adr/0014`: datierter Nachtrag mit Regel und Quelle.
- `docs/plans/m4-processing-kern.md` §3: Zeile M4-26.
- Log: Zeile zur Umsetzung. Die Zeile „Festes nodata je Ganzzahltyp“ (offen) bleibt, wie sie ist.

## 5. Grenzen und Abnahme

- Nur synthetische Fixtures, keine Anfragen an echte Quellen, keine neue Abhängigkeit.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
- Abnahme:
  - Die Tests aus §3 sind grün.
  - Alle vier Pflicht-Checks der CI sind grün.
  - Vor „fertig“ ist main geholt.
