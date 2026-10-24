# NM4-02 — Zuschnitt und Export auf die Sortierung des Mosaiks angleichen

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 2; Reihenfolge laut Log vom 24.10.2026: Stufe A neben UI-01).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch (ändert Ergebnis-Bytes).
**Start:** nach dem Merge von DOC-01. Läuft neben UI-01 und NM4-01; wer als Zweiter fertig wird, holt main.
**Startsatz:** „Führe Aufgabe NM4-02 aus `docs/plans/querschnitt/nm4-02-sortierung-zuschnitt.md` aus.“

## 1. Befund (M4-17, Frage 2, 20.10.2026)

- Alle Wege nehmen „erstes gültiges Pixel“, aber in verschiedener Reihenfolge:
  - Mosaik-Job und Mosaik-Kachel sortieren nach Ziel-CRS und Item-ID (`mosaic_order`);
  - Zuschnitt (synchron) und Export-Job folgen der Reihenfolge der Auswahl.
- Folge: In Überlappungen kann die Vorschau eine andere Szene zeigen als der Zuschnitt.

## 2. Ziel

Zuschnitt und Export verwenden **dieselbe** Sortierfunktion wie Mosaik-Job und Mosaik-Kachel. Es gibt danach genau eine Funktion für die Reihenfolge; die Session nennt sie im PR.

## 3. Umfang

1. Stellen finden, die Szenen für Zuschnitt und Export ordnen; auf die gemeinsame Funktion umstellen. Keine zweite Implementierung.
2. **Bytes und Version:** Der Zuschnitt ändert sich in Überlappungen. Der Export-Job hat einen Cache – `earthx.__version__` erhöhen (wie bei M4-26/M4-32), damit alte Ergebnisse nicht als Treffer gelten. Nachtrag in `adr/0014`.
3. **Runner:** rechnet keinen Zuschnitt (M4-16, Frage 2); im PR bestätigen, dass er nicht betroffen ist. Der lokale Hash-Vergleich (Kriterium 1) braucht danach ein neues Runner-Image nur, wenn sich die Version ändert – im PR sagen.
4. **Frontend:** Zeigt es die Reihenfolge irgendwo an oder nimmt es sie an (etwa „Crop & merge“)? Falls ja, mitziehen; sonst im PR bestätigen.

## 4. Grenzen

- Keine neue Abhängigkeit. Worker-Kern bleibt zustandslos.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests mit zwei synthetischen, überlappenden Szenen in **umgekehrter** Auswahlreihenfolge:
  - Zuschnitt, Export-Job und Mosaik-Job liefern in der Überlappung dieselben Pixel;
  - die Mosaik-Kachel zeigt dort dieselbe Szene;
  - Gegenprobe: Mit dem alten Code scheitert der Test.
- Prüfanleitung für Otto (Browser und PowerShell): zwei überlappende Szenen in beiden Reihenfolgen anhaken, „Crop & merge to AOI“ – gleiches Ergebnis, gleich wie die Vorschau.
- Alle vier Pflicht-Checks grün; Log-Zeile; Zeile im Backlog als erledigt.
- Vor „fertig“ ist main geholt.
