# Synthetische Antworten der öffentlichen STAC-API für den Chatbot

Von Hand geschrieben, nicht aufgezeichnet (wie `../earth_search/README.md`). IDs,
Titel, Ausdehnungen und Adressen sind erfunden; `example.invalid` löst nie auf.

- `collections_page_1.json` und `collections_page_2.json`: die Collection-Liste von
  `GET /stac/collections` über zwei Seiten, verbunden durch einen `next`-Link.
  Seite 2 enthält eine Collection, deren Beschreibung wie eine Anweisung an ein
  Sprachmodell aussieht. Die Tests prüfen, dass sie als Daten im Ergebnis bleibt.
- `collection_detail.json`: eine Antwort von `GET /stac/collections/{id}` mit den
  `earthx:`-Feldern, die `catalog/collection.py` schreibt.

Die Item-Suche nutzt die Dateien unter `../earth_search/`. Unsere API reicht die
Form der Seite durch (`api/federating_client.py`).
