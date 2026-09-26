# THE WALL for Home Assistant

English | [Deutsch](README.de.md)

THE WALL is a 128 x 64 LED panel for the living room. It shows aircraft flying
overhead, the time, the weather, departures, notes and what Spotify is playing.
This integration brings it into Home Assistant: switch the panel and its mode,
send notes, start timers, set the alarm and use the aircraft on the panel in
automations.

Home Assistant never talks to the device. It talks to the THE WALL server, the
same one the website and the device use. The device polls that server every two
seconds for changes, so a command from Home Assistant is on the panel in about
two seconds, without opening a port in your network.

## What you need

- A THE WALL, set up on [thewall.godart.lu](https://thewall.godart.lu) or on your
  own server with the Home Assistant API (`/api/ha/v1`).
- Home Assistant 2026.3 or newer.
- The device switched on and online while you pair it. It has to show a code.

## Installation

### With HACS

1. HACS, menu at the top right, **Custom repositories**.
2. Repository `https://github.com/LennyGodart/THE-WALL-HA`, type **Integration**.
3. Search for **THE WALL**, download it, restart Home Assistant.

### By hand

Copy the folder `custom_components/thewall` into the `custom_components` folder
of your Home Assistant configuration, so that `manifest.json` ends up at
`custom_components/thewall/manifest.json`. Restart Home Assistant.

## Setup

Each THE WALL is its own entry. Pairing works like on a TV remote: Home
Assistant asks for a code, the panel shows it, you type it in.

**Found on the network.** A device that announces itself shows up under
**Settings > Devices & services** as discovered. Select **Add**, confirm, and
the panel shows a code for five minutes.

**By device ID.** Under **Settings > Devices & services > Add integration**,
pick **THE WALL** and enter the device ID, for example `wall-7f3a91`. It is on
the website of THE WALL under **Settings**, in the **Home Assistant** section,
with a copy button. Leave the server at `https://thewall.godart.lu` unless you
run your own. Then the panel shows the code.

The code has 6 characters. Upper and lower case do not matter, spaces and
dashes are ignored. After five wrong codes the code stops working and Home
Assistant offers a new one. Asking for many codes in a row makes the server ask
you to wait a few minutes.

If the link is removed on the website or the device is deleted, the server
rejects Home Assistant. Home Assistant then asks you to pair again, and the
entities keep their IDs.

Home Assistant keeps its access token in its own configuration. The server
stores only a hash of it.

## Entities

The IDs below assume the device is called Wall and Home Assistant runs in
English. Home Assistant builds the IDs from the names in its language, so in
German they differ, see the [German README](README.de.md#entitäten).

| Entity | ID | Notes |
| --- | --- | --- |
| Light | `light.wall` | The whole panel: on, off, brightness 1 to 255 as on the website |
| Mode | `select.wall_mode` | Only the modes available: flight, clock, weather, transit, spotify, notes. Picking a mode here means you want to see it: a running rotation of two or more modes ends, the *Rotation* switches turn it back on |
| Rotation: *mode* | `switch.wall_rotation_clock` | One per mode that can rotate. Configuration, disabled by default |
| Alarm | `switch.wall_alarm` | The one alarm of the device |
| Alarm time | `time.wall_alarm_time` | HH:MM. The weekdays are set on the website |
| Note line 1, Note line 2 | `text.wall_note_line_1` | 21 characters each. Changing one line keeps the other |
| Note | `notify.wall_note` | For `notify.send_message`, see below |
| Hide note | `button.wall_hide_note` | Takes the note out of the front |
| Stop ringing | `button.wall_stop_ringing` | Dismisses ringing timers and the alarm |
| Cancel timers | `button.wall_cancel_timers` | Cancels all timers |
| Start timer | `button.wall_start_timer` | Starts a timer with the timer duration |
| Timer duration | `number.wall_timer_duration` | 1 to 240 minutes, default 5. Stays in Home Assistant |
| Timer | `sensor.wall_timer` | End of the next running timer. Attributes `timer_id`, `label`, `total`, `count` |
| Next alarm | `sensor.wall_next_alarm` | Only while the alarm is on |
| Showing | `sensor.wall_showing` | What the panel shows: a mode, or `ring`, `pairing`, `hello`, `off` |
| Callsign, Airline, Aircraft type | `sensor.wall_callsign` | The aircraft on the panel, unknown when there is none |
| Altitude, Ground speed, Distance | `sensor.wall_altitude` | In feet, knots and nautical miles. You can pick other units per entity |
| Route | `sensor.wall_route` | For example `LUX - MUC`, with the cities as attributes. Unknown when the server has no route for the flight |
| Online | `binary_sensor.wall_online` | Whether the device reaches the server. Diagnostic |
| Ringing | `binary_sensor.wall_ringing` | A timer or the alarm rings |
| Timer running | `binary_sensor.wall_timer_running` | At least one timer counts down |
| Last seen | `sensor.wall_last_seen` | Last poll of the device. Diagnostic |
| WiFi signal | `sensor.wall_wifi_signal` | In dBm. Diagnostic, disabled by default |
| Firmware | `update.wall_firmware` | **Install** asks the device to update on its next poll. Shows as in progress until it has |
| Timer | `event.wall_timer` | Event types `started`, `finished`, `cancelled` |

A new note stays in front of every mode for 10 minutes. Switching the mode or
the rotation ends that early, as on the website.

When the server cannot be reached, all entities except the timer duration
become unavailable. **Online** tells a different story: the server answers,
but the device has not polled it for a while.

## Notes from automations

```yaml
action: notify.send_message
target:
  entity_id: notify.wall_note
data:
  title: Laundry
  message: Done, 40 degrees
```

With a title, the title is line 1 and the message line 2. Without a title the
message is broken into two lines of 21 characters between words. The server
writes umlauts and accents as plain letters, so ö becomes o.

## Actions

### `thewall.start_timer`

| Field | Required | Notes |
| --- | --- | --- |
| `device_id` | no | The THE WALL. Not needed if you have only one |
| `config_entry_id` | no | Instead of `device_id` |
| `duration` | yes | 1 second to 24 hours |
| `label` | no | Up to 12 characters, shown next to the timer |

At most five timers run at the same time. Ask for the response to get the new
timer:

```yaml
action: thewall.start_timer
data:
  duration: "00:12:00"
  label: Pizza
response_variable: started
```

`started.timer` then holds `id`, `label`, `total` in seconds and `end` as ISO
8601 time.

### `thewall.cancel_timer`

Cancels the timer with `id`, or all timers without it.

```yaml
action: thewall.cancel_timer
data:
  id: "{{ started.timer.id }}"
```

## Timer events

`event.wall_timer` fires when a timer starts, finishes or is cancelled, with
the attributes `timer_id`, `label` and `total`. Home Assistant fetches the state
one second after each timer end, so `finished` is not up to 15 seconds late.

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
      entity_id: light.kitchen
    data:
      flash: short
```

## Voice control

The light carries the name of the device, so the built-in Assist sentences for
lights work: "turn off Wall", "set the brightness of Wall to 40 percent", in
German "Schalte Wall aus".

Assist has no built-in sentences for picking a mode. The blueprint in
[`blueprints/thewall_voice_modes.yaml`](blueprints/thewall_voice_modes.yaml)
adds them with a sentence trigger. Import it under **Settings > Automations &
scenes > Blueprints > Import blueprint** with this address:

```
https://github.com/LennyGodart/THE-WALL-HA/blob/main/blueprints/thewall_voice_modes.yaml
```

Create an automation from it and pick the mode select of your device. Then say
"show the clock on the wall", "put the weather on the wall" or, in German, "zeig
den Flugradar an der Wand" and "stell die Wand auf Nahverkehr". The blueprint
knows the English and German mode names and a few everyday words such as planes,
music, Flugzeuge or Musik. Copy the automation and edit its word list to add
your own.

## How often it asks

Every 15 seconds for the state, and once more one second after a timer end or
the alarm time. Commands return the new state right away, so they do not wait
for the next poll. When the server answers with "too many requests", the next
poll waits as long as the server asks.

## Removal

**Settings > Devices & services > THE WALL**, menu of the entry, **Delete**.
Home Assistant revokes its token on the server. If the server cannot be reached
at that moment, remove the link on the website under **Settings**, in the
**Home Assistant** section. Then remove the integration in HACS, or delete
`custom_components/thewall`, and restart.

## Diagnostics

The diagnostics download of the entry contains the last state and the entry
data. The token is removed from it.

## Development

```
pip install -r requirements_test.txt
python -m pytest tests -q
```

The tests use a fake server and never touch the network. They also run on
Windows: `tests/windows_compat.py` fills in the Unix modules the Home Assistant
test harness imports and lets the event loop create its internal socket pair.
On Linux and macOS that file does nothing. For the shims to come first,
`pyproject.toml` blocks the entry point of the test plugin and
`tests/conftest.py` loads it itself.

`python tools/make_icon.py` draws `brand/icon.png` and `icon@2x.png` from the 5
x 7 font of the panel.

`tests_live/` runs against a real server instead of the fake one, with real HTTP
and the real pairing code from the server's database. It is not part of the
normal run and needs a server in development mode with SQLite, plus
`THEWALL_LIVE_SERVER` (for example `http://127.0.0.1:8765`), `THEWALL_LIVE_KEY`
(the API key of an account there) and `THEWALL_LIVE_DB` (the path to its
database). Run it with `python -m pytest tests_live -q`. It pairs through the
config flow, uses every kind of entity, lets a timer run out, stops the ringing
and unpairs again.

## License

MIT, like the rest of THE WALL.
