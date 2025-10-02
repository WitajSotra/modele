# CTranslator Webservice

## Bauen des Containers

`docker build -t ctranslator_v2 .
`
## Starten des Containers

`docker run -d -p 25000:5000 --mount type=bind,source=$(pwd)/version.txt,target=/app/version.txt -it ctranslator_v2`

## Test

`curl http://localhost:25000/info`

Returns information on available models and translation directions.

`curl -X POST http://localhost:25000/translate -H "Content-Type: application/json" -d '{"text": "Dies ist ein Test. Test.\nTest2.\n\nTest3. Test4.\n" , "source_language":"de", "target_language":"hsb" }'`

In the translate call you can set an optional "model" parameter that sets which model will be used for the translation.

## Modellkonfiguration
Die Modelle müssen im Ordner `models` abgelegt werden. Die Datei `model_config.yaml` enthält die Information, welche Modelle für welche Sprachrichtungen genutzt werden können. Das erste Modell in der Liste ist das Default-Modell für die jeweilige Sprache, das genutzt wird, wenn im `/translate`-Call kein Modell angegeben wird. Dabei wird jedes Modell durch den Namen des Unterordners identifiziert, in dem das Modell abgelegt ist.

Jedes Modell ist in einem eigenen Unterordner in `models` abgelegt. Dabei sind die folgenden Dateien nötig:
- model_info.yaml: Datei mit Metadaten und Konfigurationen zum Modell. Hier sind insbesondere die Einstellungen gesetzt, wie das Modell vom Webservice behandelt werden soll (siehe unten).
- codes-yttm: Modell für die im Training verwendete BPE-Kodierung.
- config.json: Konfigurationsdatei, die beim Erstellen des ctranslate-Modells erstellt wird.
- model.bin: Von CTranslate erstellte Modell-Binärdatei.
- shared_vocabulary.json: Ebenfalls von CTranslate erstellt.
- train_vocabulary.txt: Set aller Token in Trainings-, Test- und Validierungsdateien für alle von diesem Modell abgedeckten Sprachen.  


Felder in model_info.yaml:
| Feld  | mögliche Werte | Beschreibung |
|-------|----------------|--------------|
| name  |                | Name des Modells |
| directions|            | Unterstützte Übersetzungsrichtungen, abgebildet als Liste von Strings im Format "Quellsprache_Zielsprache", z.B. "de_hsb".|
| tokenizer_languages |           | Für jede Sprache sollte die zu verwendende Spracheinstellung für den Sacremoses-Tokenizer abgebildet werden. Wenn z.B. für die Obersorbischen Inputs der Tokenizer mit Einstellung "cs" verwendet werden soll, muss entsprechend der Eintag "hsb: cs" gesetzt werden. |
|custom_nonbreaking_prefix_files | | Pfad zum nonbreaking_prefix_file für den Tokenizer für die Sprachen, wo ein solches benutzt werden soll. |
|sentence_splitter_nonbreaking_prefix_files | | Pfad zum nonbreaking_prefix_file zum sentence splitting für die Sprachen, wo ein solches benutzt werden soll. (Betrifft bei den existierenden Modellen spezifisch hsb und dsb). |
| protected_pattern_file | | Pfad zur Datei mit protected patterns, falls solche vom Tokenizer verwendet werden sollen. |
| escape_xml | true, false | Ob XML-Symbole im Tokenizer escaped werden sollen. Sollte der Einstellung entsprechen, die auch im Training benutzt wurde. |
| placeholder_handling_method | named_entity_id, ph_mark, keine | Die Methode, die zur Ersetzung von Emailadressen, URLs, Zahlen etc. mit Platzhaltern verwendet wird. `named_entity_id` ersetzt die relevanten Zeichenketten mit einer Zahl. Das ist die Methode, die aus dem Frontend übernommen wurde. Sie ist vor allem für die LMU-Modelle relevant. `ph_mark` ersetzt die Zeichenketten mit dem String '⟦⟧'. Diese Methode kommt bei Modellen zum Einsatz, die damit trainiert wurde; insbesondere die von Olaf Langner trainieren Modelle. |
| return_unks | true, false | Gib beim `translate`-Aufruf die unbekannten Tokens zurück. Funktioniert nur, wenn für ein Modell ein `train_vocabulary.txt` hinterlegt ist. |

| aggressive_dash_splits | true, false | Setting für den Tokenizer. Sollten denselben Wert haben, der im Training verwendet wurde. |
