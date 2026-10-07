# M4-08a-fix2 — Shutdown-Test beim Abholen nicht stabil: Plan und Befund

**Aufgabe:** M4-08a-fix2 (Nachbesserung zu M4-08a, PR #124).
**Stufe B** wegen eines möglichen Wettlaufs im Aufseher. Ergebnis: Die Ursache
liegt **nur im Test**; laut Auftrag direkt behoben, kein Halt.
**Ort im Repo:** `docs/plans/m4-08a-fix2.md`
**Grundlagen:** `adr/0013` §5.2, §5.6; `plans/m4-08a-jobs-queue.md` §3.4
(„Herunterfahren“, K5); `plans/m4-processing-kern.md` §3.
**Befund aus PR #131:**
`backend/tests/earthx/jobs/test_worker.py::TestShutdown::test_a_run_picked_up_in_the_moment_of_the_shutdown_is_given_back_before_a_child_starts`
fällt im Einzellauf mal, mal nicht.

---

## 1. Ergebnis in drei Sätzen

Der Aufseher gibt einen beim Herunterfahren abgeholten Lauf korrekt zurück und
startet kein Kind dafür; in keinem Fehlschlag blieb eine Lease stehen. Der Test
las Status und Versuchsnummer in **zwei** Abfragen: Fiel das Abholen zwischen
beide, sah er „wartend“ (vorher) und „Versuch 1“ (nachher) und prüfte `worker`
und `lease_until`, bevor der Aufseher die Lease 6–10 ms später freigab. Der
Test liest beide Spalten jetzt in einer Abfrage; 500 Läufe ohne Fehlschlag,
die Gegenprobe zeigt den alten Fehler.

---

## 2. Messung vorher: 200 Einzelläufe

Je Lauf ein eigener `pytest`-Aufruf nur dieses Tests (eigene Wegwerf-Datenbank
je Aufruf, wie im Befund). Ein temporäres pytest-Plugin (nicht eingecheckt)
liest bei einem Fehlschlag die Zeile von `earthx_run` sofort nach der
fehlgeschlagenen Zusicherung, noch vor dem Abbau.

- **Fehlerrate: 12 von 200 (6 %).**
- **Stelle:** alle 12 an derselben Zusicherung,
  `run_row(db, …, "worker", "lease_until") == (None, None)`, mit
  `('test-0', <Zeitpunkt>)`. Die Zusicherung davor (`started == []`) hielt in
  allen 12.

Zustand bei Fehlschlag, gleich in allen 12:

| | in der Zusicherung | wenige ms danach (Plugin) |
|---|---|---|
| Lauf (`status`) | — (nicht gelesen) | `accepted` |
| Versuch (`attempt`) | 1 | 1 |
| `worker` | `test-0` | leer |
| Lease (`lease_until`) | gesetzt | leer |
| `error_kind` | — | `lease_lost` (Freigabe nach K5) |
| Kind gestartet | nein | nein |

Abstand zwischen Abholen (`started_at`) und Freigabe (`not_before`, gesetzt
von `release` mit Wartezeit 0): 6–10 ms.

## 3. Ursache

**Nicht im Aufseher.** Geprüft in `jobs/worker.py` (`_slot`) und
`jobs/queue.py` (`claim`, `release`, `finish_failed`):

- `claim` setzt `status = 'running'` und `attempt + 1` in **einer**
  Anweisung und einer Transaktion. Den Zustand „`accepted`, Versuch 1“ gibt es
  in der Datenbank erst nach `release`.
- Abholen und Freigeben laufen im selben Slot-Thread nacheinander; nach der
  Freigabe verlässt der Slot die Schleife (`break`), nichts holt den Lauf in
  diesem Aufseher wieder ab.
- In allen 12 Fehlschlägen war die Zeile Millisekunden später vollständig
  freigegeben, ohne Kind. Kein Fehlschlag zeigt eine stehende Lease, einen
  zweiten Versuch oder ein gestartetes Kind.

**Im Test.** Die Wartebedingung war

```python
_state(db, job_id) == "accepted" and run_row(db, _run_id(db), "attempt")[0] == 1
```

also zwei Abfragen. Ablauf eines Fehlschlags:

1. Erste Abfrage (`job_status`): Lauf noch `accepted`, Versuch 0 (vor dem
   Abholen).
2. Der Slot holt ab: `running`, Versuch 1, `worker`, Lease.
3. Zweite Abfrage: Versuch 1 → Bedingung wahr, obwohl der Lauf läuft.
4. Die Zusicherung liest `worker` und `lease_until`, bevor `release` 6–10 ms
   später committet → rot.

Das ist eine Zeitannahme des Tests (zwei Lesezugriffe gelten als ein Bild),
kein Wettlauf zwischen Abholen und Herunterfahren.

**Nebenbefund ohne Änderung:** Kommt `stop()` zwischen der Prüfung von
`_stopping` nach dem Abholen und `_start_child`, startet ein Kind und wird in
der ersten Runde von `_watch` beendet; der Lauf geht über `_conclude` →
`release` zurück. Die Lease wird also auch dann sofort freigegeben (K5);
nur lebt ein Kind kurz. Das widerspricht `plans/m4-08a-jobs-queue.md` §3.4
nicht und ist nicht Gegenstand dieses Tests.

## 4. Behebung (nur Test)

`test_worker.py`, nur dieser Test:

- Die Kennung des Laufs einmal vor dem Start lesen.
- Warten, bis `status` und `attempt` **in einer Abfrage** `("accepted", 1)`
  sind; dieser Zustand entsteht nur durch die Freigabe.
- Dann wie bisher: kein Kind gestartet, `worker` und `lease_until` leer; dazu
  der Job-Status `accepted` über `job_status`.

Keine Änderung an `jobs/`, keine längeren Wartezeiten.

## 5. Messung nachher und Gegenprobe

Gegenproben mit einem zweiten temporären Plugin, das nur Zeitfenster weitet
(Pause nach `_state`, Verzögerung vor `queue.release`), Logik unverändert; dazu
eigene Arbeitsbäume außerhalb des Repos:

| Probe | Läufe | Ergebnis |
|---|---|---|
| neuer Test, unverändert | 500 | **500 grün, 0 rot** |
| A: alter Test, Pause 50 ms zwischen den zwei Abfragen, Freigabe 300 ms verzögert | 20 | 20 rot, alle mit dem alten Fehler (`('test-0', …) == (None, None)`) |
| B: neuer Test, dieselben Fenster | 20 | 20 grün |
| C: neuer Test gegen einen Aufseher **ohne** die Rückgabe beim Herunterfahren (4 Zeilen in `_slot` entfernt) | 3 | 3 rot (Lauf kommt nicht zurück, Wartebedingung läuft ab) |

A zeigt den Mechanismus des alten Fehlers, B, dass der neue Test ihn nicht
mehr hat, C, dass der neue Test den echten Fehler im Aufseher weiter fängt.

## 6. Prüfungen

- `pytest` aus der Repo-Wurzel: 3109 bestanden (lief während der 500 Läufe
  gleichzeitig, also unter zusätzlicher Last).
- `ruff check backend`: sauber.
- `lint-imports --config .importlinter` (`PYTHONPATH=backend`): 14 Verträge
  gehalten, 0 gebrochen.
- CI-Lauf: siehe Checks des PR.
