# ADR 0035 — Darstellung der Ergebnisse eines Operators (Looks)

- **Status:** **Angenommen** (Otto, 2026-11-16), umgesetzt mit seinem Nachtrag vom selben Tag. Bestätigt sind auch die Auslegungen: fester Bereich bei Aspect (Auto-scale in Perzentilen schaltet auf Werte 0/360), 0/100 bei Hillshade, 2/98 bei Slope, und Bänder von Aufträgen ohne geladene Beschreibung bekommen keinen Look (§4 Punkt 1). Die Nummer 0035 war beim Start frei; beim Merge prüfen, ob ein anderer PR sie inzwischen hat.
- **Aufgabe:** Nachtrag zu M5-10 (Geländeoperator `terrain`), im PR UI-09 ([#366](https://github.com/oscipal/earthX/pull/366)). Stufe A, weil Otto die Vorgaben selbst gemacht hat; der Ort der Vorgabe ist die einzige Entscheidung von Claude.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §2 (Funktionen auf Datensätze übertragen), `projektuebersicht.md` (Registry statt Sonderfälle im Code), `adr/0030` (Operator-Art `focal`), `adr/0023` F5.

## 1. Vorgabe (Otto, 16.11.2026)

Die Produkte des Operators `terrain` werden in Vorschau, Ergebnis-Layer und angehefteten Ebenen so gezeichnet, und zwar als **Registry-/Operator-Vorgabe, nicht im Frontend-Code je Datensatz**:

| Produkt | Colormap | Skala | „Auto-scale“ |
|---|---|---|---|
| Slope | `rdylgn_r` (flach grün, steil rot) | die übliche der Messung (2.–98. Perzentil) | wie bisher |
| Hillshade | `greys_r` (dunkel → hell, beleuchtete Hänge hell) | 0–100 % Perzentil (Minimum bis Maximum) | 0 und 100 |
| Aspect | `hsv` (zyklisch) | fest 0–360° | 0 und 360, jede Himmelsrichtung überall dieselbe Farbe |

## 2. Optionen für den Ort der Vorgabe

| | Option | Für | Gegen |
|---|---|---|---|
| A | Tabelle im Frontend (Produkt → Look) | wenig Aufwand | Wissen über ein Produkt im Frontend, bei jedem Operator neu; ausdrücklich nicht gewollt |
| B | Je Datensatz in der Registry (wie `index_presets`) | Vorbild vorhanden | dieselbe Vorgabe für jeden Datensatz mit `terrain` wiederholt; Index-Presets hängen an einem Ausdruck, nicht an einem Produkt |
| C | **Am Operator** (`Operator.looks`), in der Prozessbeschreibung als `x-earthx-looks` **(Empfehlung, umgesetzt)** | eine Stelle für alle Datensätze; das Frontend liest nur, wie bei `x-earthx-passes-values`; neue Produkte brauchen kein Frontend | ein Feld mehr am Operator und in der Beschreibung |

## 3. Entscheidung (Entwurf): Option C

- `backend/earthx/processing/operators/base.py`: `Look(colormap, scale, low, high)` mit `scale` ∈ `measured` (2.–98. Perzentil der Messung), `percentiles` (`low`–`high` %, nur 0–100 und 2–98 sind aus der Messung bekannt), `fixed` (feste Zahlen). `Looks(param, by_value)` wählt den Look nach einem Parameter des Schritts (`terrain`: `product`). Ein unvollständiger Look wirft beim Anlegen.
- `terrain.py` setzt die drei Looks aus §1; ein Test hält fest, dass der Tiler jede Colormap kennt.
- `api/processing_docs.py`: `x-earthx-looks` am Schritt; Schritte ohne Looks tragen nichts. Die Fixtures unter `frontend/src/fixtures/processes/` sind neu geschrieben.
- Frontend: `displayLook.ts` liest die Beschreibung (unvollständige Looks werden verworfen) und rechnet Look und Messung zu Bereich und Colormap. Vorschau (`PreviewSpec.look`, `drawnRange`, `adoptMeasure`) und Ergebnis (`ResultBand.look`, `presetOfResultBand`, `ResultLayerInfo.look`) nehmen sie; angeheftete Ebenen erben die gezeichnete Kachel-URL bzw. `ResultLayerInfo.preset`. Der Look der Ebene geht nach dem Preset eines Index (gleiche Rangfolge wie für Indizes) und vor der üblichen Regel der Messung; ein Bereich, den der Nutzer anwandte, geht vor beiden.
- „Auto-scale“ setzt nur den Bereich zurück, die gewählte Colormap bleibt (Otto, 16.11.2026, gleicher Tag); in Perzentilen nimmt es die des Looks (Hillshade 0/100, sonst 2/98); ein fester Bereich (Aspect) ist keine Perzentile, die Felder gehen auf Werte 0/360.

## 4. Grenzen und offene Punkte

1. **Beschreibung nicht geladen:** Der Look eines Ergebnisbands wird beim Lesen der Ergebnisse aus der Beschreibung des Datensatzes bestimmt; sie liegt vor, wenn der Auftrag aus dem Panel gestartet wurde. Bänder von Aufträgen, die vor diesem Stand gelesen und gespeichert wurden, haben keinen Look und werden wie bisher gezeichnet.
2. **Mehrere Schritte:** Die Vorschau zeichnet nur bis zum ersten Schritt, der keine Pixelrechnung ist (`focal` beendet die Kette); der Look gilt für das Band dieses Schritts.
3. **Perzentile über Minimum/Maximum und 2/98 hinaus** kennt die Messung nicht (`percentile_N` gibt es erst über „Apply“ in Perzentilen); ein Look mit anderen Perzentilen fällt auf die übliche Skala zurück. Für die drei Produkte reicht es.
4. **Weitere Operatoren** (TRI, TPI, Krümmung, P3) tragen ihren Look am selben Feld ein.
5. **Pyramiden und Ersatz** (M5-30): Die Farbskala bleibt über allen Zoomstufen dieselbe wie über `min_zoom` (M5-10-Plan, Abschnitt zur Farbskala unter `min_zoom`); der Look ändert daran nichts, weil er Teil der Kachel-URL ist.

## 5. Nachtrag M5-60 (21.11.2026): Looks auch je Band

Ein Band der Quelle hat einen Look derselben Form (`plans/m5/m5-60-darstellung-je-band.md`, Otto 21.11.2026: F1–F7 je Option 1). `Look` liegt deshalb in `catalog/registry.py` statt in `processing/operators/base.py` (`catalog` darf `processing` nicht importieren, umgekehrt schon). Die Registry löst ihn je Band auf (`DatasetConfig.look_of`): Ausnahme von Hand > Quelle (`band_looks`) > Standardbild bzw. H1 > feste Regel nach Einheit (`UNIT_LOOKS`) > `DEFAULT_LOOK`; die Collection veröffentlicht ihn je Band in `earthx:bands` als `earthx:look` mit `earthx:look_origin`. Die Rangfolge in der Oberfläche bleibt: Hand > Preset > Look (Operator oder Band) > übliche Messung.
