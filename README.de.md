# THE WALL für Home Assistant

[English](README.md) | Deutsch

THE WALL ist ein LED-Panel fürs Wohnzimmer mit 128 mal 64 Pixeln. Es zeigt
Flugzeuge über dem Haus, die Uhrzeit, das Wetter, Abfahrten, Notizen und was
auf Spotify läuft. Diese Integration holt es in Home Assistant: Panel und Modus
schalten, Notizen schicken, Timer starten, den Wecker stellen und das Flugzeug
auf dem Panel in Automationen verwenden.

Home Assistant spricht nie mit dem Gerät. Es spricht mit dem Server von THE
WALL, demselben, den Webseite und Gerät benutzen. Das Gerät fragt den Server
alle zwei Sekunden nach Änderungen. Ein Befehl aus Home Assistant steht deshalb
nach etwa zwei Sekunden auf dem Panel, ohne dass im Heimnetz ein Port offen
sein muss.

## Was du brauchst

- THE WALL, eingerichtet auf [thewall.godart.lu](https://thewall.godart.lu)
  oder auf einem eigenen Server mit der Home-Assistant-Schnittstelle
  (`/api/ha/v1`).
- Home Assistant 2026.3 oder neuer.
- Das Gerät eingeschaltet und online, während du es koppelst. Es muss einen Code
  zeigen können.

## Installation

### Mit HACS

1. HACS, Menü oben rechts, **Benutzerdefinierte Repositories**.
2. Repository `https://github.com/LennyGodart/THE-WALL-HA`, Typ **Integration**.
3. Nach **THE WALL** suchen, herunterladen, Home Assistant neu starten.

### Von Hand

Den Ordner `custom_components/thewall` in den Ordner `custom_components` der
Home-Assistant-Konfiguration kopieren, sodass `manifest.json` unter
`custom_components/thewall/manifest.json` liegt. Home Assistant neu starten.

## Einrichtung

Jedes Gerät ist ein eigener Eintrag. Gekoppelt wird wie bei einer
TV-Fernbedienung: Home Assistant bittet um einen Code, das Panel zeigt ihn, du
tippst ihn ein.

**Im Netzwerk gefunden.** Ein Gerät, das sich im Netzwerk meldet, erscheint
unter **Einstellungen > Geräte & Dienste** als gefunden. **Hinzufügen** wählen,
bestätigen, und das Panel zeigt fünf Minuten lang einen Code.

**Mit der Geräte-ID.** Unter **Einstellungen > Geräte & Dienste > Integration
hinzufügen** **THE WALL** wählen und die Geräte-ID eingeben, zum Beispiel
`wall-7f3a91`. Sie steht auf der Webseite von THE WALL unter **Einstellungen**
im Abschnitt **Home Assistant**, mit Knopf zum Kopieren. Den Server auf
`https://thewall.godart.lu` lassen, außer du betreibst einen eigenen. Danach
zeigt das Panel den Code.

Der Code hat 6 Zeichen. Groß- und Kleinschreibung spielt keine Rolle,
Leerzeichen und Bindestriche werden ignoriert. Nach fünf falschen Codes gilt der
Code nicht mehr, und Home Assistant bietet einen neuen an. Wer viele Codes
hintereinander anfordert, muss ein paar Minuten warten, das verlangt der Server.

Wird die Kopplung auf der Webseite entfernt oder das Gerät gelöscht, lehnt der
Server Home Assistant ab. Home Assistant bittet dann um eine neue Kopplung, die
Entitäten behalten ihre IDs.

Home Assistant bewahrt seinen Zugangsschlüssel in der eigenen Konfiguration auf.
Der Server speichert davon nur einen Hash.

## Entitäten

Die IDs gelten für ein Gerät namens Wall in einem Home Assistant auf Deutsch. In
einem englischen Home Assistant heißen sie anders, siehe das
[englische README](README.md#entities).

| Entität | ID | Hinweise |
| --- | --- | --- |
| Licht | `light.wall` | Das ganze Panel: an, aus, Helligkeit 1 bis 255 wie auf der Webseite |
| Modus | `select.wall_modus` | Nur die verfügbaren Modi: flight, clock, weather, transit, spotify, notes. Wer hier einen Modus wählt, will ihn sehen: eine laufende Rotation mit zwei oder mehr Modi endet dann, die Schalter *Rotation* schalten sie wieder an |
| Rotation: *Modus* | `switch.wall_rotation_uhr` | Einer je Modus, der in die Rotation kann. Konfiguration, anfangs deaktiviert |
| Wecker | `switch.wall_wecker` | Der eine Wecker des Geräts |
| Weckzeit | `time.wall_weckzeit` | HH:MM. Die Wochentage stellst du auf der Webseite ein |
| Notiz Zeile 1, Notiz Zeile 2 | `text.wall_notiz_zeile_1` | Je 21 Zeichen. Wer eine Zeile ändert, behält die andere |
| Notiz | `notify.wall_notiz` | Für `notify.send_message`, siehe unten |
| Notiz ausblenden | `button.wall_notiz_ausblenden` | Nimmt die Notiz aus dem Vordergrund |
| Klingeln beenden | `button.wall_klingeln_beenden` | Beendet klingelnde Timer und den Wecker |
| Timer abbrechen | `button.wall_timer_abbrechen` | Bricht alle Timer ab |
| Timer starten | `button.wall_timer_starten` | Startet einen Timer mit der Timerdauer |
| Timerdauer | `number.wall_timerdauer` | 1 bis 240 Minuten, anfangs 5. Bleibt in Home Assistant |
| Timer | `sensor.wall_timer` | Ende des nächsten laufenden Timers. Attribute `timer_id`, `label`, `total`, `count` |
| Nächster Wecker | `sensor.wall_nachster_wecker` | Nur solange der Wecker an ist |
| Anzeige | `sensor.wall_anzeige` | Was das Panel zeigt: einen Modus oder `ring`, `pairing`, `hello`, `off` |
| Rufzeichen, Airline, Flugzeugtyp | `sensor.wall_rufzeichen` | Das Flugzeug auf dem Panel, unbekannt wenn keines da ist |
| Flughöhe, Geschwindigkeit über Grund, Entfernung | `sensor.wall_flughohe` | In Fuß, Knoten und Seemeilen. Andere Einheiten lassen sich je Entität wählen |
| Strecke | `sensor.wall_strecke` | Zum Beispiel `LUX - MUC`, die Städte als Attribute. Unbekannt, wenn der Server keine Strecke zum Flug hat |
| Online | `binary_sensor.wall_online` | Ob das Gerät den Server erreicht. Diagnose |
| Klingelt | `binary_sensor.wall_klingelt` | Ein Timer oder der Wecker klingelt |
| Timer läuft | `binary_sensor.wall_timer_lauft` | Mindestens ein Timer zählt herunter |
| Zuletzt gesehen | `sensor.wall_zuletzt_gesehen` | Letzter Abruf des Geräts. Diagnose |
| WLAN-Signal | `sensor.wall_wlan_signal` | In dBm. Diagnose, anfangs deaktiviert |
| Firmware | `update.wall_firmware` | **Installieren** bittet das Gerät, sich beim nächsten Abruf zu aktualisieren. Bis dahin steht das Update als laufend da |
| Timer | `event.wall_timer` | Ereignisse `started`, `finished`, `cancelled` |

Eine neue Notiz steht zehn Minuten lang vor jedem Modus. Ein Wechsel von Modus
oder Rotation beendet das früher, wie auf der Webseite.

Ist der Server nicht erreichbar, werden alle Entitäten außer der Timerdauer
unverfügbar. **Online** meint etwas anderes: Der Server antwortet, aber das Gerät
hat sich eine Weile nicht gemeldet.

## Notizen aus Automationen

```yaml
action: notify.send_message
target:
  entity_id: notify.wall_notiz
data:
  title: Wäsche
  message: Fertig, 40 Grad
```

Mit Titel ist der Titel Zeile 1 und die Nachricht Zeile 2. Ohne Titel wird die
Nachricht zwischen den Wörtern auf zwei Zeilen zu 21 Zeichen verteilt. Der
Server schreibt Umlaute und Akzente als einfache Buchstaben, aus ö wird o.

## Aktionen

### `thewall.start_timer`

| Feld | Pflicht | Hinweise |
| --- | --- | --- |
| `device_id` | nein | Das Gerät. Bei nur einem Gerät nicht nötig |
| `config_entry_id` | nein | Statt `device_id` |
| `duration` | ja | 1 Sekunde bis 24 Stunden |
| `label` | nein | Bis zu 12 Zeichen, steht neben dem Timer |

Höchstens fünf Timer laufen gleichzeitig. Wer die Antwort anfordert, bekommt
den neuen Timer zurück:

```yaml
action: thewall.start_timer
data:
  duration: "00:12:00"
  label: Pizza
response_variable: started
```

`started.timer` enthält dann `id`, `label`, `total` in Sekunden und `end` als
Zeit nach ISO 8601.

### `thewall.cancel_timer`

Bricht den Timer mit `id` ab, ohne `id` alle Timer.

```yaml
action: thewall.cancel_timer
data:
  id: "{{ started.timer.id }}"
```

## Timer-Ereignisse

`event.wall_timer` meldet, wenn ein Timer startet, abläuft oder abgebrochen
wird, mit den Attributen `timer_id`, `label` und `total`. Home Assistant fragt
eine Sekunde nach jedem Timerende nach, deshalb kommt `finished` nicht bis zu 15
Sekunden zu spät.

```yaml
triggers:
  - trigger: state
    entity_id: event.wall_timer
conditions:
  - condition: state
    entity_id: event.wall_timer
    attribute: event_type
    state: finished
actions:
  - action: light.turn_on
    target:
      entity_id: light.kueche
    data:
      flash: short
```

## Sprachsteuerung

Das Licht trägt den Namen des Geräts, deshalb funktionieren die eingebauten
Assist-Sätze für Lichter: "Schalte Wall aus", "Schalte Wall ein", auf Englisch
"set the brightness of Wall to 40 percent".

Für die Wahl eines Modus hat Assist keine eingebauten Sätze. Die Vorlage in
[`blueprints/thewall_voice_modes.yaml`](blueprints/thewall_voice_modes.yaml)
ergänzt sie mit einem Satz-Auslöser. Importieren unter **Einstellungen >
Automationen & Szenen > Vorlagen > Vorlage importieren** mit dieser Adresse:

```
https://github.com/LennyGodart/THE-WALL-HA/blob/main/blueprints/thewall_voice_modes.yaml
```

Daraus eine Automation anlegen und die Modus-Auswahl des Geräts wählen, hier
`select.wall_modus`. Danach versteht Assist "zeig den Flugradar an der Wand",
"zeige das Wetter an der Wand" und "stell die Wand auf Nahverkehr", auf Englisch
etwa "show the clock on the wall". Die Vorlage kennt die deutschen und englischen
Modusnamen und ein paar Alltagswörter wie Flugzeuge, Uhrzeit oder Musik. Wer
eigene Wörter will, kopiert die Automation und ergänzt die Wortliste.

## Wie oft es fragt

Alle 15 Sekunden nach dem Stand und einmal zusätzlich eine Sekunde nach einem
Timerende oder der Weckzeit. Befehle bringen den neuen Stand gleich mit und
warten nicht auf die nächste Abfrage. Antwortet der Server mit "zu viele
Anfragen", wartet die nächste Abfrage so lange, wie der Server verlangt.

## Entfernen

**Einstellungen > Geräte & Dienste > THE WALL**, Menü des Eintrags,
**Löschen**. Home Assistant zieht dabei seinen Schlüssel auf dem Server zurück.
Ist der Server in dem Moment nicht erreichbar, die Kopplung auf der Webseite
unter **Einstellungen** im Abschnitt **Home Assistant** entfernen. Danach die
Integration in HACS entfernen oder `custom_components/thewall` löschen und neu
starten.

## Diagnose

Der Diagnose-Download des Eintrags enthält den letzten Stand und die Daten des
Eintrags. Der Schlüssel ist darin entfernt.

## Entwicklung

```
pip install -r requirements_test.txt
python -m pytest tests -q
```

Die Tests laufen gegen einen nachgebauten Server und gehen nie ins Netz. Sie
laufen auch unter Windows: `tests/windows_compat.py` ergänzt die Unix-Module, die
das Testgerüst von Home Assistant importiert, und erlaubt der Ereignisschleife
ihr internes Socket-Paar. Unter Linux und macOS tut die Datei nichts. Damit die
Ergänzungen zuerst greifen, sperrt `pyproject.toml` den Einstiegspunkt des
Test-Plugins, und `tests/conftest.py` lädt es selbst.

`python tools/make_icon.py` zeichnet `brand/icon.png` und `icon@2x.png` aus der
5-mal-7-Schrift des Panels.

`tests_live/` ist ein Durchlauf gegen einen echten Server statt des
nachgebauten, mit echtem HTTP und dem echten Kopplungscode aus der Datenbank des
Servers. Er gehört nicht zum normalen Lauf und braucht einen Server im
Entwicklungsmodus mit SQLite, dazu `THEWALL_LIVE_SERVER` (etwa
`http://127.0.0.1:8765`), `THEWALL_LIVE_KEY` (API-Schlüssel eines Kontos dort)
und `THEWALL_LIVE_DB` (Pfad zu dessen Datenbank). Aufruf:
`python -m pytest tests_live -q`. Er koppelt über die Einrichtung, schaltet jede
Art von Entität, lässt einen Timer ablaufen, stoppt das Klingeln und trennt
wieder.

## Lizenz

MIT, wie der Rest von THE WALL.
