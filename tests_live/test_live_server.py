"""THE WALL integration against a real server, pairing included.

Needs a THE WALL server in development mode with SQLite, for example
web/ of the main repo started with `TW_ENV=dev php -S 127.0.0.1:8765 -t web
tools/dev-router.php`, and three variables:

    THEWALL_LIVE_SERVER  http://127.0.0.1:8765
    THEWALL_LIVE_KEY     API key of an account on that server (tw_live_...)
    THEWALL_LIVE_DB      path to its SQLite database, to read the pairing code

The test plays the device itself: it polls /api/v1/frame with the account key,
so the server knows the device and shows the pairing code. Then it pairs through
the real config flow, uses every kind of entity and checks what the server and
the panel got. Run: `python -m pytest tests_live -q`.
"""

from __future__ import annotations

import asyncio
from datetime import time
import os
import sqlite3
import time as systime
from typing import Any
import uuid

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.thewall.const import CONF_TOKEN, DOMAIN

SERVER = os.environ.get("THEWALL_LIVE_SERVER", "").rstrip("/")
KEY = os.environ.get("THEWALL_LIVE_KEY", "")
DB = os.environ.get("THEWALL_LIVE_DB", "")

pytestmark = pytest.mark.skipif(
    not (SERVER and KEY and DB),
    reason="needs THEWALL_LIVE_SERVER, THEWALL_LIVE_KEY and THEWALL_LIVE_DB",
)


class Device:
    """Polls like the firmware, at most once a second like the server allows."""

    def __init__(self, http: aiohttp.ClientSession, uid: str) -> None:
        """Poll as the device with this ID."""
        self.http = http
        self.uid = uid
        self._last = 0.0

    async def frame(self) -> dict[str, Any]:
        """Fetch a frame like the firmware does."""
        wait = 1.15 - (systime.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = systime.monotonic()
        async with self.http.get(
            f"{SERVER}/api/v1/frame",
            headers={
                "Authorization": f"Bearer {KEY}",
                "X-Wall-Id": self.uid,
                "X-Wall-Fw": "0.2.1",
            },
        ) as resp:
            assert resp.status == 200, await resp.text()
            return await resp.json()


def pairing_code(uid: str) -> str:
    """Read the code the panel shows from the server's database."""
    con = sqlite3.connect(DB)
    try:
        row = con.execute(
            "SELECT p.code FROM ha_pairings p JOIN devices d ON d.id = p.device_id"
            " WHERE d.uid = ? ORDER BY p.created_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
    finally:
        con.close()
    assert row, "no pairing on the server"
    return row[0]


async def server_state(http: aiohttp.ClientSession, token: str) -> dict[str, Any]:
    """Fetch the state as the server sees it, past Home Assistant."""
    async with http.get(
        f"{SERVER}/api/ha/v1/state", headers={"Authorization": f"Bearer {token}"}
    ) as resp:
        data = await resp.json()
        return {"status": resp.status, **data}


def entity_id(hass: HomeAssistant, platform: str, uid: str, key: str) -> str:
    """Find an entity of this device by its key."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{uid}_{key}")
    assert found, f"no {platform} {key}"
    return found


async def test_live_server(hass: HomeAssistant, socket_enabled: None) -> None:
    """Pair, control, watch a timer ring, stop it and unpair, all for real."""
    uid = f"wall-live{uuid.uuid4().hex[:4]}"
    async with aiohttp.ClientSession() as http:
        device = Device(http, uid)
        first = await device.frame()
        assert first["pages"], "the server sent no pages"

        # Pairing through the real config flow.
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device_id": uid.upper(), "server": SERVER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "pair"

        panel = await device.frame()
        assert panel["pages"][0]["mode"] == "pairing"
        code = pairing_code(uid)
        texts = [op.get("s") for op in panel["pages"][0]["ops"] if op["t"] == "text"]
        assert f"{code[:3]} {code[3:]}" in texts

        wrong = "AAAAAA" if code != "AAAAAA" else "CCCCCC"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": wrong}
        )
        assert result["errors"] == {"base": "invalid_code"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": f"{code[:3].lower()}-{code[3:].lower()}"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        entry = result["result"]
        token = entry.data[CONF_TOKEN]
        assert token.startswith("twha_")
        await hass.async_block_till_done()

        after = await device.frame()
        assert after["pages"][0].get("mode") != "pairing"

        # Entities exist and show the server's state.
        light = entity_id(hass, "light", uid, "panel")
        select = entity_id(hass, "select", uid, "mode")
        assert hass.states.get(light).state == "on"
        server = await server_state(http, token)
        assert hass.states.get(select).state == server["state"]["panel"]["mode"]

        # Panel off and on with brightness.
        await hass.services.async_call(
            "light", "turn_off", {"entity_id": light}, blocking=True
        )
        server = await server_state(http, token)
        assert server["state"]["panel"]["on"] is False
        assert (await device.frame())["bright"] == 0
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": light, "brightness": 100},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["panel"]["on"] is True
        assert server["state"]["panel"]["bright"] == 100
        assert hass.states.get(light).attributes["brightness"] == 100

        # Mode.
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": select, "option": "clock"},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["panel"]["mode"] == "clock"
        assert (await device.frame())["pages"][0]["mode"] == "clock"

        # A note through notify, then hidden with the button.
        notify = entity_id(hass, "notify", uid, "note")
        await hass.services.async_call(
            "notify",
            "send_message",
            {"entity_id": notify, "title": "Waschmaschine", "message": "ist fertig"},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["note"]["line1"] == "Waschmaschine"
        assert server["state"]["note"]["line2"] == "ist fertig"
        assert server["state"]["note"]["front_left"] > 590
        assert (await device.frame())["pages"][0]["mode"] == "notes"
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, "button", uid, "hide_note")},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["note"]["front_left"] == 0

        # One note line through the text entity keeps the other.
        await hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": entity_id(hass, "text", uid, "note_line1"), "value": "Hallo"},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["note"]["line1"] == "Hallo"
        assert server["state"]["note"]["line2"] == "ist fertig"

        # Timers: the action with a response, then the number and button.
        response = await hass.services.async_call(
            DOMAIN,
            "start_timer",
            {"duration": {"minutes": 2}, "label": "Tee"},
            blocking=True,
            return_response=True,
        )
        assert response
        server = await server_state(http, token)
        assert [t["label"] for t in server["state"]["timers"]] == ["Tee"]
        frame = await device.frame()
        corner = [
            op
            for op in frame["pages"][0]["ops"]
            if op["t"] == "count" and op["x"] == 128
        ]
        assert corner, "no timer corner on the panel"
        assert frame["timers"] == [server["state"]["timers"][0]["end"] * 1000]
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, "number", uid, "timer_duration"), "value": 3},
            blocking=True,
        )
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, "button", uid, "start_timer")},
            blocking=True,
        )
        server = await server_state(http, token)
        assert sorted(t["total"] for t in server["state"]["timers"]) == [120, 180]
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, "button", uid, "cancel_timers")},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["timers"] == []

        # Alarm time and switch.
        await hass.services.async_call(
            "time",
            "set_value",
            {
                "entity_id": entity_id(hass, "time", uid, "alarm_time"),
                "time": time(6, 45),
            },
            blocking=True,
        )
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id(hass, "switch", uid, "alarm")},
            blocking=True,
        )
        server = await server_state(http, token)
        assert server["state"]["alarm"]["on"] is True
        assert server["state"]["alarm"]["time"] == "06:45"
        assert server["state"]["alarm"]["next"]
        next_alarm = entity_id(hass, "sensor", uid, "next_alarm")
        assert hass.states.get(next_alarm).state not in ("unknown", "unavailable")

        # A short timer runs out: the coordinator refreshes right after it, the
        # ringing sensor turns on, the event fires, the panel shows the ring page.
        await hass.services.async_call(
            DOMAIN, "start_timer", {"duration": {"seconds": 2}}, blocking=True
        )
        await asyncio.sleep(4.5)
        await hass.async_block_till_done()
        ringing = entity_id(hass, "binary_sensor", uid, "ringing")
        assert hass.states.get(ringing).state == "on"
        event = entity_id(hass, "event", uid, "timer")
        assert hass.states.get(event).attributes.get("event_type") == "finished"
        assert (await device.frame())["pages"][0]["mode"] == "ring"
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, "button", uid, "stop_ringing")},
            blocking=True,
        )
        assert hass.states.get(ringing).state == "off"
        assert (await device.frame())["pages"][0]["mode"] != "ring"

        # No newer firmware on a development server: Home Assistant refuses the
        # install itself, before the entity is asked.
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "update",
                "install",
                {"entity_id": entity_id(hass, "update", uid, "firmware")},
                blocking=True,
            )

        # Removing the entry revokes the token on the server.
        assert await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        server = await server_state(http, token)
        assert server["status"] == 401
        assert server["code"] == "invalid_token"
